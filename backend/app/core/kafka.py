"""Kafka client factories and topic administration."""

from __future__ import annotations

import json
import logging
import ssl
from typing import Any

from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
from aiokafka.admin import AIOKafkaAdminClient, NewTopic
from aiokafka.errors import TopicAlreadyExistsError

from app.core.config import get_settings

logger = logging.getLogger(__name__)


def _security_kwargs() -> dict[str, Any]:
    s = get_settings()
    kwargs: dict[str, Any] = {"security_protocol": s.kafka_security_protocol}
    if s.kafka_security_protocol in ("SSL", "SASL_SSL"):
        ctx = ssl.create_default_context(cafile=s.kafka_ssl_cafile) if s.kafka_ssl_cafile else ssl.create_default_context()
        kwargs["ssl_context"] = ctx
    if s.kafka_security_protocol.startswith("SASL"):
        kwargs["sasl_mechanism"] = s.kafka_sasl_mechanism or "SCRAM-SHA-512"
        kwargs["sasl_plain_username"] = s.kafka_sasl_username
        kwargs["sasl_plain_password"] = (
            s.kafka_sasl_password.get_secret_value() if s.kafka_sasl_password else None
        )
    return kwargs


def _serialize(value: Any) -> bytes:
    return json.dumps(value, default=str, separators=(",", ":")).encode("utf-8")


def make_producer() -> AIOKafkaProducer:
    s = get_settings()
    return AIOKafkaProducer(
        bootstrap_servers=s.kafka_bootstrap_servers,
        client_id=f"{s.kafka_client_id}-producer",
        acks="all",
        enable_idempotence=True,
        linger_ms=10,
        compression_type="gzip",
        value_serializer=_serialize,
        key_serializer=lambda k: k.encode("utf-8") if k else None,
        **_security_kwargs(),
    )


def make_consumer(group_id: str, *topics: str) -> AIOKafkaConsumer:
    s = get_settings()
    return AIOKafkaConsumer(
        *topics,
        bootstrap_servers=s.kafka_bootstrap_servers,
        client_id=f"{s.kafka_client_id}-{group_id}",
        group_id=group_id,
        enable_auto_commit=False,
        auto_offset_reset="earliest",
        isolation_level="read_committed",
        max_poll_records=100,
        value_deserializer=lambda b: json.loads(b.decode("utf-8")),
        **_security_kwargs(),
    )


async def ensure_topics() -> None:
    s = get_settings()
    admin = AIOKafkaAdminClient(bootstrap_servers=s.kafka_bootstrap_servers, **_security_kwargs())
    await admin.start()
    try:
        existing = set(await admin.list_topics())
        wanted = [
            NewTopic(
                name=topic,
                num_partitions=s.kafka_topic_partitions,
                replication_factor=s.kafka_replication_factor,
                # Long retention so consumers (audit, analytics) can replay history.
                topic_configs={"retention.ms": str(retention), "cleanup.policy": "delete"},
            )
            for topic, retention in (
                (s.kafka_topic_domain_events, 90 * 86400 * 1000),
                (s.kafka_topic_field_events, 30 * 86400 * 1000),
                (s.kafka_topic_dlq, 180 * 86400 * 1000),
            )
            if topic not in existing
        ]
        if wanted:
            try:
                await admin.create_topics(wanted)
                logger.info("created kafka topics", extra={"topics": [t.name for t in wanted]})
            except TopicAlreadyExistsError:
                pass
    finally:
        await admin.close()
