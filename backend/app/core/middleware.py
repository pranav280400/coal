"""Cross-cutting HTTP middleware: request ids, security headers, rate limiting."""

from __future__ import annotations

import logging
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.config import get_settings
from app.core.logging import request_id_ctx
from app.core.redis import get_redis

logger = logging.getLogger("cmg.access")


def client_ip(request: Request) -> str:
    """Resolve the client IP honouring exactly TRUSTED_PROXY_COUNT reverse proxies."""
    trusted = get_settings().trusted_proxy_count
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded and trusted > 0:
        hops = [h.strip() for h in forwarded.split(",") if h.strip()]
        if len(hops) >= trusted:
            return hops[-trusted]
    return request.client.host if request.client else "unknown"


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        incoming = request.headers.get("x-request-id", "")
        rid = incoming if 8 <= len(incoming) <= 64 and incoming.replace("-", "").isalnum() else uuid.uuid4().hex
        token = request_id_ctx.set(rid)
        start = time.perf_counter()
        try:
            response = await call_next(request)
        finally:
            request_id_ctx.reset(token)
        response.headers["X-Request-ID"] = rid
        if request.url.path not in ("/health/live", "/health/ready", "/metrics"):
            logger.info(
                "%s %s %s",
                request.method,
                request.url.path,
                response.status_code,
                extra={
                    "request_id": rid,
                    "duration_ms": round((time.perf_counter() - start) * 1000, 1),
                    "client_ip": client_ip(request),
                },
            )
        return response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        response.headers.setdefault("Cache-Control", "no-store")
        if not request.url.path.startswith(("/docs", "/redoc")):
            response.headers.setdefault("Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'")
        if get_settings().is_production:
            response.headers.setdefault("Strict-Transport-Security", "max-age=63072000; includeSubDomains")
        return response


_AUTH_PATH_MARKERS = ("/auth/login", "/auth/register", "/auth/forgot-password", "/auth/reset-password", "/auth/refresh")


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Fixed-window limiter in Redis keyed by client IP (stricter for auth endpoints).

    Fails open if Redis is unavailable so an outage of the cache does not take the
    whole platform down; this is logged loudly.
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        path = request.url.path
        if path.startswith(("/health", "/metrics")) or request.method == "OPTIONS":
            return await call_next(request)
        settings = get_settings()
        is_auth = any(marker in path for marker in _AUTH_PATH_MARKERS)
        limit = settings.rate_limit_auth_per_minute if is_auth else settings.rate_limit_per_minute
        window = int(time.time() // 60)
        key = f"cmg:rl:{'auth' if is_auth else 'api'}:{client_ip(request)}:{window}"
        try:
            redis = get_redis()
            pipe = redis.pipeline()
            pipe.incr(key)
            pipe.expire(key, 65)
            count, _ = await pipe.execute()
        except Exception:  # pragma: no cover - availability over strictness
            logger.error("rate limiter unavailable; failing open")
            return await call_next(request)
        remaining = max(0, limit - int(count))
        if int(count) > limit:
            return JSONResponse(
                {"type": "https://coalminegov.gov.in/problems/rate_limited", "title": "Rate limited",
                 "status": 429, "detail": "Too many requests, please retry shortly."},
                status_code=429,
                headers={"Retry-After": str(60 - int(time.time()) % 60), "X-RateLimit-Limit": str(limit)},
                media_type="application/problem+json",
            )
        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        return response
