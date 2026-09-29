"""Domain events via the transactional outbox.

State changes and their events are committed in the same database transaction;
the outbox relay then publishes to Kafka. This guarantees that the audit trail,
notifications and analytics never miss a change even if Kafka is briefly down.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models import OutboxEvent
from app.services.access import Principal

SCHEMA_VERSION = 1


def build_envelope(
    event_type: str,
    *,
    entity_type: str,
    entity_id: Any,
    actor: Principal | None,
    mine_id: Any = None,
    subsidiary_id: Any = None,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    data: dict[str, Any] | None = None,
    event_id: uuid.UUID | None = None,
    occurred_at: datetime | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "event_id": str(event_id or uuid.uuid4()),
        "event_type": event_type,
        "occurred_at": (occurred_at or datetime.now(UTC)).isoformat(),
        "entity_type": entity_type,
        "entity_id": str(entity_id),
        "mine_id": str(mine_id) if mine_id else None,
        "subsidiary_id": str(subsidiary_id) if subsidiary_id else None,
        "actor": actor.as_dict() if actor else {"id": None, "role": "system", "name": "System"},
        "before": before,
        "after": after,
        "data": data or {},
    }


def record_event(session: AsyncSession, event_type: str, **kwargs: Any) -> dict[str, Any]:
    """Stage a domain event in the outbox; it is committed with the caller's transaction."""
    envelope = build_envelope(event_type, **kwargs)
    session.add(
        OutboxEvent(
            event_id=uuid.UUID(envelope["event_id"]),
            topic=get_settings().kafka_topic_domain_events,
            # Partition by mine so per-mine ordering is preserved and load spreads across mines.
            key=envelope["mine_id"] or envelope["entity_id"],
            payload=envelope,
        )
    )
    return envelope
