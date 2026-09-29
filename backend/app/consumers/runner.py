"""Consumer process entrypoint.

    python -m app.consumers.runner                       # all consumers + outbox relay
    python -m app.consumers.runner audit notifications   # a subset (scale independently)
"""

from __future__ import annotations

import asyncio
import logging
import signal
import sys

from prometheus_client import start_http_server

from app.consumers.base import run_consumer
from app.consumers.handlers import (
    handle_analytics,
    handle_audit,
    handle_ingest,
    handle_notifications,
    handle_orchestrator,
)
from app.consumers.outbox import run_outbox_relay
from app.core.config import get_settings
from app.core.db import dispose_engine
from app.core.kafka import ensure_topics, make_producer
from app.core.logging import configure_logging
from app.core.redis import close_redis

logger = logging.getLogger("cmg.consumers")

ALL = ("outbox", "audit", "notifications", "analytics", "orchestrator", "ingest")


async def main(selected: list[str]) -> None:
    configure_logging("consumers")
    s = get_settings()
    start_http_server(s.consumer_metrics_port)
    for attempt in range(30):
        try:
            await ensure_topics()
            break
        except Exception as exc:
            logger.warning("kafka not ready (attempt %s): %s", attempt + 1, exc)
            await asyncio.sleep(min(2 + attempt, 10))
    producer = make_producer()
    await producer.start()
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop.set)
        except NotImplementedError:
            pass
    domain = [s.kafka_topic_domain_events]
    tasks: list[asyncio.Task[None]] = []
    spec = {
        "audit": lambda: run_consumer("audit", domain, handle_audit, stop, producer),
        "notifications": lambda: run_consumer("notifications", domain, handle_notifications, stop, producer),
        "analytics": lambda: run_consumer("analytics", domain, handle_analytics, stop, producer),
        "orchestrator": lambda: run_consumer("orchestrator", domain, handle_orchestrator, stop, producer),
        "ingest": lambda: run_consumer("ingest", [s.kafka_topic_field_events], handle_ingest, stop, producer,
                                       event_id_key="client_event_id"),
        "outbox": lambda: run_outbox_relay(producer, stop),
    }
    for name in selected:
        tasks.append(asyncio.create_task(spec[name](), name=name))
    logger.info("running consumers: %s", ", ".join(selected))
    try:
        await stop.wait()
    finally:
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await producer.stop()
        await close_redis()
        await dispose_engine()


if __name__ == "__main__":
    names = sys.argv[1:] or list(ALL)
    unknown = set(names) - set(ALL)
    if unknown:
        raise SystemExit(f"unknown consumers: {sorted(unknown)}; choose from {ALL}")
    asyncio.run(main(names))
