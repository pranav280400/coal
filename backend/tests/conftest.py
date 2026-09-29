"""Test fixtures.

Integration tests run against a real PostgreSQL (set TEST_DATABASE_URL, e.g.
postgresql+asyncpg://cmg@127.0.0.1:5432/coalminegov_test). Redis is replaced by
fakeredis, object storage by an in-memory store, and Kafka/Temporal are made
unreachable so the tests also prove the graceful-degradation paths.
"""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest

TEST_DB = os.environ.get("TEST_DATABASE_URL")
os.environ.setdefault("LOG_JSON", "false")
os.environ["ENVIRONMENT"] = "test"
os.environ["TEMPORAL_HOST"] = "127.0.0.1:1"
os.environ["KAFKA_BOOTSTRAP_SERVERS"] = "127.0.0.1:1"
os.environ["LLM_BASE_URL"] = "http://127.0.0.1:1/v1"
os.environ["QDRANT_URL"] = "http://127.0.0.1:1"
os.environ["RATE_LIMIT_AUTH_PER_MINUTE"] = "10000"
if TEST_DB:
    os.environ["DATABASE_URL"] = TEST_DB

BACKEND = Path(__file__).resolve().parents[1]


def pytest_collection_modifyitems(config: Any, items: list[Any]) -> None:
    if TEST_DB:
        return
    skip = pytest.mark.skip(reason="set TEST_DATABASE_URL to run integration tests")
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip)


@pytest.fixture(scope="session")
def migrated_db() -> None:
    """Fresh schema via Alembic (exactly what production runs)."""
    code = (
        "import asyncio\n"
        "from sqlalchemy import text\n"
        "from sqlalchemy.ext.asyncio import create_async_engine\n"
        "import os\n"
        "async def main():\n"
        "    e = create_async_engine(os.environ['DATABASE_URL'])\n"
        "    async with e.begin() as c:\n"
        "        await c.execute(text('DROP SCHEMA public CASCADE'))\n"
        "        await c.execute(text('CREATE SCHEMA public'))\n"
        "    await e.dispose()\n"
        "asyncio.run(main())\n"
    )
    subprocess.run([sys.executable, "-c", code], check=True, cwd=BACKEND)
    subprocess.run([sys.executable, "-m", "app.cli", "migrate"], check=True, cwd=BACKEND)


class MemoryStorage:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    async def put_object(self, key: str, data: bytes, content_type: str, metadata: Any = None) -> None:
        self.objects[key] = data

    async def get_object(self, key: str) -> bytes:
        return self.objects[key]

    async def presigned_get_url(self, key: str, filename: str | None = None, inline: bool = False) -> str:
        return f"https://storage.test/{key}?sig=test"

    async def ensure_bucket(self) -> None:
        return None

    async def ping(self) -> bool:
        return True


@pytest.fixture(scope="session")
async def app_client(migrated_db: None) -> AsyncIterator[Any]:
    import fakeredis
    import httpx

    from app.core import redis as redis_mod
    from app.core import storage
    from app.workflows import client as temporal

    redis_mod._client = fakeredis.FakeAsyncRedis(decode_responses=True)
    mem = MemoryStorage()
    for name in ("put_object", "get_object", "presigned_get_url", "ensure_bucket", "ping"):
        setattr(storage, name, getattr(mem, name))

    signals: list[tuple[str, str, Any]] = []

    async def fake_signal(workflow_id: str, signal_name: str, arg: Any = None) -> bool:
        signals.append((workflow_id, signal_name, arg))
        return True

    temporal.signal = fake_signal  # type: ignore[assignment]

    import app.main as main_mod

    async def no_producer() -> None:
        return None

    main_mod.get_event_producer = no_producer  # type: ignore[assignment]
    transport = httpx.ASGITransport(app=main_mod.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        client.signals = signals  # type: ignore[attr-defined]
        client.storage = mem  # type: ignore[attr-defined]
        yield client
    from app.core.db import dispose_engine

    await dispose_engine()
