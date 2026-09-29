"""FastAPI application: the Lumen API gateway."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from aiokafka import AIOKafkaProducer
from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from sqlalchemy import text

from app import __version__
from app.ai import vectorstore
from app.api.v1 import (
    ai,
    auth,
    compliance,
    contractors,
    field,
    governance,
    grievances,
    notifications,
    operations,
    org,
)
from app.core import storage
from app.core.config import get_settings
from app.core.db import dispose_engine, get_engine
from app.core.errors import register_exception_handlers
from app.core.kafka import make_producer
from app.core.logging import configure_logging
from app.core.metrics import PrometheusMiddleware
from app.core.middleware import RateLimitMiddleware, RequestContextMiddleware, SecurityHeadersMiddleware
from app.core.redis import close_redis, get_redis
from app.workflows import client as temporal

logger = logging.getLogger(__name__)

_producer: AIOKafkaProducer | None = None
_producer_lock = asyncio.Lock()


async def get_event_producer() -> AIOKafkaProducer | None:
    """Lazily started Kafka producer for mobile ingest; None while Kafka is unreachable."""
    global _producer
    async with _producer_lock:
        if _producer is None:
            producer = make_producer()
            try:
                await asyncio.wait_for(producer.start(), timeout=5)
            except Exception as exc:
                logger.warning("kafka producer unavailable: %s", exc)
                try:
                    await producer.stop()
                except Exception:
                    pass
                return None
            _producer = producer
    return _producer


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    configure_logging("api")
    settings = get_settings()
    logger.info("starting %s API v%s (%s)", settings.app_name, __version__, settings.environment)
    get_engine()
    try:
        await storage.ensure_bucket()
    except Exception as exc:
        logger.warning("object storage not ready at startup: %s", exc)
    from app.api.v1.ai import warm_assistant

    warm = asyncio.create_task(warm_assistant())
    yield
    warm.cancel()
    global _producer
    if _producer is not None:
        await _producer.stop()
        _producer = None
    await close_redis()
    await dispose_engine()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Lumen API",
        version=__version__,
        description="AI-based Smart Governance & Compliance Monitoring System for Coal Mines (PS 26024)",
        lifespan=lifespan,
        docs_url=None if settings.is_production else "/docs",
        redoc_url=None if settings.is_production else "/redoc",
        openapi_url=None if settings.is_production else "/openapi.json",
    )
    register_exception_handlers(app)
    # Starlette applies middleware in reverse order of registration (last added = outermost).
    app.add_middleware(GZipMiddleware, minimum_size=1024)
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(PrometheusMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
        expose_headers=["X-Request-ID", "X-RateLimit-Remaining"],
        max_age=600,
    )
    app.add_middleware(RequestContextMiddleware)

    for router in (auth.router, org.router, compliance.router, field.router, contractors.router,
                   governance.router, notifications.router, ai.router, grievances.router, operations.router):
        app.include_router(router, prefix=settings.api_prefix)

    @app.get("/health/live", include_in_schema=False)
    async def live() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/health/ready", include_in_schema=False)
    async def ready(response: Response) -> dict[str, object]:
        checks: dict[str, bool] = {}
        try:
            async with get_engine().connect() as conn:
                await conn.execute(text("SELECT 1"))
            checks["postgres"] = True
        except Exception:
            checks["postgres"] = False
        try:
            checks["redis"] = bool(await get_redis().ping())
        except Exception:
            checks["redis"] = False
        # Degraded dependencies are reported but only Postgres/Redis gate readiness.
        checks["object_storage"] = await storage.ping()
        checks["temporal"] = await temporal.health()
        checks["qdrant"] = await vectorstore.health()
        ok = checks["postgres"] and checks["redis"]
        response.status_code = 200 if ok else 503
        return {"status": "ready" if ok else "not_ready", "checks": checks, "version": __version__}

    @app.get("/metrics", include_in_schema=False)
    async def metrics() -> Response:
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    return app


app = create_app()
