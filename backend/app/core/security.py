"""Password hashing (Argon2id), JWT access tokens and rotating refresh tokens."""

from __future__ import annotations

import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from app.core.config import get_settings
from app.core.redis import get_redis

_hasher = PasswordHasher(time_cost=3, memory_cost=64 * 1024, parallelism=2)

# A pre-computed hash used to equalise timing when the username does not exist.
_DUMMY_HASH = _hasher.hash("timing-equaliser-not-a-real-password")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str | None) -> bool:
    try:
        return _hasher.verify(password_hash or _DUMMY_HASH, password) and password_hash is not None
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def needs_rehash(password_hash: str) -> bool:
    return _hasher.check_needs_rehash(password_hash)


def validate_password_strength(password: str) -> list[str]:
    settings = get_settings()
    problems: list[str] = []
    if len(password) < settings.password_min_length:
        problems.append(f"must be at least {settings.password_min_length} characters")
    if not any(c.islower() for c in password):
        problems.append("must contain a lowercase letter")
    if not any(c.isupper() for c in password):
        problems.append("must contain an uppercase letter")
    if not any(c.isdigit() for c in password):
        problems.append("must contain a digit")
    if not any(not c.isalnum() for c in password):
        problems.append("must contain a symbol")
    return problems


@dataclass(slots=True)
class TokenPair:
    access_token: str
    refresh_token: str
    access_expires_at: datetime
    refresh_expires_at: datetime


class TokenError(Exception):
    pass


def _now() -> datetime:
    return datetime.now(UTC)


def create_access_token(user_id: str, role: str, extra: dict[str, Any] | None = None) -> tuple[str, datetime]:
    settings = get_settings()
    expires = _now() + timedelta(minutes=settings.access_token_ttl_minutes)
    payload: dict[str, Any] = {
        "sub": user_id,
        "role": role,
        "type": "access",
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "iat": int(_now().timestamp()),
        "exp": int(expires.timestamp()),
        "jti": uuid.uuid4().hex,
    }
    if extra:
        payload.update(extra)
    token = jwt.encode(payload, settings.jwt_secret_key.get_secret_value(), algorithm=settings.jwt_algorithm)
    return token, expires


def decode_access_token(token: str) -> dict[str, Any]:
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key.get_secret_value(),
            algorithms=[settings.jwt_algorithm],
            audience=settings.jwt_audience,
            issuer=settings.jwt_issuer,
            options={"require": ["exp", "sub", "iat", "jti"]},
        )
    except jwt.PyJWTError as exc:
        raise TokenError(str(exc)) from exc
    if payload.get("type") != "access":
        raise TokenError("wrong token type")
    return payload


# ------------------------------------------------------------------ refresh
# Refresh tokens are opaque random strings. Redis stores
#   cmg:rt:<token-id>  -> "<user_id>:<family_id>"   (TTL = refresh lifetime)
#   cmg:rtf:<family>   -> "active"|"revoked"
# Every use rotates the token. Re-use of a rotated token revokes the whole
# family (refresh-token theft detection, RFC 6819 §5.2.2.3).

_RT_PREFIX = "cmg:rt:"
_RTF_PREFIX = "cmg:rtf:"
_USER_FAMILIES = "cmg:rtu:"


async def issue_token_pair(user_id: str, role: str, family_id: str | None = None) -> TokenPair:
    settings = get_settings()
    redis = get_redis()
    access, access_exp = create_access_token(user_id, role)
    family = family_id or uuid.uuid4().hex
    token_id = secrets.token_urlsafe(48)
    ttl = int(timedelta(days=settings.refresh_token_ttl_days).total_seconds())
    pipe = redis.pipeline()
    pipe.set(f"{_RT_PREFIX}{token_id}", f"{user_id}:{family}", ex=ttl)
    pipe.set(f"{_RTF_PREFIX}{family}", "active", ex=ttl)
    pipe.sadd(f"{_USER_FAMILIES}{user_id}", family)
    pipe.expire(f"{_USER_FAMILIES}{user_id}", ttl)
    await pipe.execute()
    return TokenPair(access, token_id, access_exp, _now() + timedelta(seconds=ttl))


async def rotate_refresh_token(refresh_token: str) -> tuple[str, str]:
    """Consume a refresh token. Returns (user_id, family_id) or raises TokenError."""
    redis = get_redis()
    value = await redis.getdel(f"{_RT_PREFIX}{refresh_token}")
    if value is None:
        used = await redis.get(f"{_RT_PREFIX}used:{refresh_token}")
        if used:
            # Replay of an already-rotated token → revoke the family.
            await redis.set(f"{_RTF_PREFIX}{used}", "revoked", keepttl=True)
        raise TokenError("refresh token invalid or expired")
    user_id, family = value.split(":", 1)
    status = await redis.get(f"{_RTF_PREFIX}{family}")
    if status != "active":
        raise TokenError("refresh token family revoked")
    ttl = int(timedelta(days=get_settings().refresh_token_ttl_days).total_seconds())
    await redis.set(f"{_RT_PREFIX}used:{refresh_token}", family, ex=ttl)
    return user_id, family


async def revoke_refresh_token(refresh_token: str) -> None:
    redis = get_redis()
    value = await redis.getdel(f"{_RT_PREFIX}{refresh_token}")
    if value:
        _, family = value.split(":", 1)
        await redis.set(f"{_RTF_PREFIX}{family}", "revoked", keepttl=True)


async def revoke_all_user_sessions(user_id: str) -> None:
    redis = get_redis()
    families = await redis.smembers(f"{_USER_FAMILIES}{user_id}")
    if families:
        pipe = redis.pipeline()
        for family in families:
            pipe.set(f"{_RTF_PREFIX}{family}", "revoked", keepttl=True)
        await pipe.execute()
    # Access tokens issued before this instant are rejected by the auth dependency.
    await redis.set(f"cmg:revoked-before:{user_id}", int(_now().timestamp()), ex=86400 * 30)


async def access_token_revoked(user_id: str, issued_at: int) -> bool:
    cutoff = await get_redis().get(f"cmg:revoked-before:{user_id}")
    return cutoff is not None and issued_at <= int(cutoff)


# --------------------------------------------------------------- lockout
async def register_failed_login(identifier: str) -> int:
    settings = get_settings()
    redis = get_redis()
    key = f"cmg:login-fail:{identifier.lower()}"
    count = await redis.incr(key)
    if count == 1:
        await redis.expire(key, settings.login_lockout_minutes * 60)
    return int(count)


async def is_locked_out(identifier: str) -> bool:
    count = await get_redis().get(f"cmg:login-fail:{identifier.lower()}")
    return count is not None and int(count) >= get_settings().login_max_attempts


async def clear_failed_logins(identifier: str) -> None:
    await get_redis().delete(f"cmg:login-fail:{identifier.lower()}")


def generate_opaque_token(nbytes: int = 32) -> str:
    return secrets.token_urlsafe(nbytes)
