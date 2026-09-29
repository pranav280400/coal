"""Generic at-least-once Kafka consumer loop with idempotent effects and a DLQ."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from aiokafka import AIOKafkaProducer, TopicPartition
from aiokafka.structs import ConsumerRecord
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import session_scope
from app.core.kafka import make_consumer
from app.core.metrics import EVENTS_CONSUMED
from app.models import ProcessedEvent

logger = logging.getLogger(__name__)

Handler = Callable[[AsyncSession, dict[str, Any]], Awaitable[None]]

MAX_ATTEMPTS = 5


async def claim(session: AsyncSession, consumer: str, event_id: str) -> bool:
    """Insert into the idempotency ledger; False if this consumer already processed the event."""
    result = await session.execute(
        insert(ProcessedEvent).values(consumer=consumer, event_id=event_id).on_conflict_do_nothing()
    )
    return bool(result.rowcount)


async def run_consumer(
    name: str,
    topics: list[str],
    handler: Handler,
    stop: asyncio.Event,
    dlq_producer: AIOKafkaProducer | None,
    *,
    event_id_key: str = "event_id",
    type_key: str = "event_type",
) -> None:
    """Consume ``topics`` as consumer group ``cmg-<name>``.

    Each record is handled inside one DB transaction together with its
    idempotency claim, so a crash between effect and commit simply re-processes
    (and is deduplicated). Poison messages go to the DLQ after MAX_ATTEMPTS.
    """
    while not stop.is_set():
        consumer = make_consumer(f"cmg-{name}", *topics)
        try:
            await consumer.start()
            logger.info("consumer %s started on %s", name, topics)
            while not stop.is_set():
                batch = await consumer.getmany(timeout_ms=1000, max_records=100)
                for tp, records in batch.items():
                    for record in records:
                        await _handle_record(name, record, handler, dlq_producer, event_id_key, type_key)
                        await consumer.commit({TopicPartition(tp.topic, tp.partition): record.offset + 1})
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error("consumer %s crashed, restarting in 5s: %s", name, exc)
            await asyncio.sleep(5)
        finally:
            try:
                await consumer.stop()
            except Exception:
                pass
    logger.info("consumer %s stopped", name)


async def _handle_record(
    name: str,
    record: ConsumerRecord,
    handler: Handler,
    dlq: AIOKafkaProducer | None,
    event_id_key: str,
    type_key: str,
) -> None:
    event: dict[str, Any] = record.value if isinstance(record.value, dict) else {}
    event_id = str(event.get(event_id_key) or f"{record.topic}:{record.partition}:{record.offset}")
    event_type = str(event.get(type_key, "unknown"))
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            async with session_scope() as session:
                if not await claim(session, name, event_id):
                    EVENTS_CONSUMED.labels(name, event_type, "duplicate").inc()
                    return
                await handler(session, event)
            EVENTS_CONSUMED.labels(name, event_type, "ok").inc()
            return
        except Exception as exc:
            logger.warning("consumer %s failed on %s (attempt %s): %s", name, event_type, attempt, exc,
                           exc_info=attempt == MAX_ATTEMPTS)
            await asyncio.sleep(min(2 ** attempt, 30))
    EVENTS_CONSUMED.labels(name, event_type, "dead_letter").inc()
    if dlq is not None:
        try:
            await dlq.send_and_wait(
                get_settings().kafka_topic_dlq,
                {"consumer": name, "topic": record.topic, "partition": record.partition, "offset": record.offset,
                 "event": event},
                key=event_id,
            )
        except Exception as exc:
            logger.error("DLQ publish failed for %s: %s", event_id, exc)
