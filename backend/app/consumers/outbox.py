"""Transactional-outbox relay: publishes committed domain events to Kafka in order."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta

from aiokafka import AIOKafkaProducer
from sqlalchemy import delete, func, select

from app.core.db import session_scope
from app.core.metrics import EVENTS_PUBLISHED, OUTBOX_BACKLOG
from app.models import OutboxEvent

logger = logging.getLogger(__name__)

BATCH = 200
RETENTION = timedelta(days=7)


async def relay_once(producer: AIOKafkaProducer) -> int:
    """Publish one batch. Rows are locked with SKIP LOCKED so several relays can run safely."""
    async with session_scope() as session:
        rows = (
            await session.execute(
                select(OutboxEvent)
                .where(OutboxEvent.published_at.is_(None))
                .order_by(OutboxEvent.id)
                .limit(BATCH)
                .with_for_update(skip_locked=True)
            )
        ).scalars().all()
        if not rows:
            return 0
        now = datetime.now(UTC)
        futures = []
        for row in rows:
            row.attempts += 1
            futures.append((row, await producer.send(row.topic, row.payload, key=row.key)))
        for row, fut in futures:
            await fut  # raises on broker failure → whole batch rolls back and is retried
            row.published_at = now
            EVENTS_PUBLISHED.labels(row.topic, row.payload.get("event_type", "unknown")).inc()
        return len(rows)


async def run_outbox_relay(producer: AIOKafkaProducer, stop: asyncio.Event) -> None:
    logger.info("outbox relay started")
    last_cleanup = datetime.min.replace(tzinfo=UTC)
    while not stop.is_set():
        try:
            sent = await relay_once(producer)
            if datetime.now(UTC) - last_cleanup > timedelta(hours=1):
                async with session_scope() as session:
                    await session.execute(
                        delete(OutboxEvent).where(OutboxEvent.published_at < datetime.now(UTC) - RETENTION)
                    )
                    backlog = (
                        await session.execute(select(func.count()).where(OutboxEvent.published_at.is_(None)))
                    ).scalar_one()
                    OUTBOX_BACKLOG.set(backlog)
                last_cleanup = datetime.now(UTC)
            if sent == 0:
                await asyncio.sleep(0.5)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error("outbox relay error: %s", exc)
            await asyncio.sleep(3)
    logger.info("outbox relay stopped")
