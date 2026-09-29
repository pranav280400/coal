"""Shared async Redis client."""

from __future__ import annotations

import json
from typing import Any

from redis.asyncio import Redis

from app.core.config import get_settings

_client: Redis | None = None


def get_redis() -> Redis:
    global _client
    if _client is None:
        _client = Redis.from_url(
            get_settings().redis_url.get_secret_value(),
            decode_responses=True,
            health_check_interval=30,
            socket_timeout=5,
            socket_connect_timeout=5,
        )
    return _client


async def close_redis() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
    _client = None


async def cache_get_json(key: str) -> Any | None:
    raw = await get_redis().get(key)
    return json.loads(raw) if raw else None


async def cache_set_json(key: str, value: Any, ttl_seconds: int) -> None:
    await get_redis().set(key, json.dumps(value, default=str), ex=ttl_seconds)


async def cache_delete_pattern(pattern: str) -> int:
    client = get_redis()
    deleted = 0
    async for key in client.scan_iter(match=pattern, count=500):
        deleted += await client.delete(key)
    return deleted


# Channel used to fan real-time notifications out to SSE connections.
NOTIFY_CHANNEL_PREFIX = "cmg:notify:"


def user_channel(user_id: str) -> str:
    return f"{NOTIFY_CHANNEL_PREFIX}{user_id}"
