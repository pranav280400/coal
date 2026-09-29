"""Mobile/offline field-event ingestion (FR4, NFR offline resilience).

Flow: PWA queues events in IndexedDB → POST /ingest/events (batch) → Kafka
``cmg.field-events`` (keyed by mine for per-mine ordering) → ingest consumer
materialises them into Postgres. ``client_event_id`` makes every step
idempotent, so retries after flaky connectivity never create duplicates.
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.core.metrics import INGEST_EVENTS
from app.core.redis import get_redis
from app.models import User
from app.models.enums import UserStatus
from app.schemas.field import AttendanceCreate, IngestEvent, InspectionCreate, ViolationCreate
from app.services import contractors as contractor_svc
from app.services import inspections as inspection_svc
from app.services import violations as violation_svc
from app.services.access import Principal

logger = logging.getLogger(__name__)

STATUS_TTL = 7 * 86400


def status_key(client_event_id: str) -> str:
    return f"cmg:ingest:{client_event_id}"


async def set_status(client_event_id: str, status: str, *, entity_type: str | None = None,
                     entity_id: str | None = None, detail: str | None = None) -> None:
    await get_redis().set(
        status_key(client_event_id),
        json.dumps({"status": status, "entity_type": entity_type, "entity_id": entity_id, "detail": detail}),
        ex=STATUS_TTL,
    )


async def get_statuses(ids: list[str]) -> dict[str, Any]:
    if not ids:
        return {}
    values = await get_redis().mget([status_key(i) for i in ids])
    return {i: (json.loads(v) if v else {"status": "queued"}) for i, v in zip(ids, values, strict=True)}


async def process(session: AsyncSession, user_id: uuid.UUID, event: IngestEvent) -> tuple[str, str | None, str | None]:
    """Materialise one field event. Returns (status, entity_type, entity_id)."""
    user = await session.get(User, user_id)
    if user is None or user.status != UserStatus.ACTIVE:
        raise PermissionError("submitting user is no longer active")
    principal = Principal.from_user(user)
    payload = {**event.payload, "client_event_id": event.client_event_id}
    try:
        if event.event_type == "inspection.submitted":
            payload.setdefault("inspected_at", event.captured_at.isoformat())
            obj, created = await inspection_svc.create_inspection(
                session, principal, InspectionCreate.model_validate(payload), source="mobile"
            )
            entity_type = "inspection"
        elif event.event_type == "violation.reported":
            payload.setdefault("occurred_at", event.captured_at.isoformat())
            obj, created = await violation_svc.create_violation(
                session, principal, ViolationCreate.model_validate(payload)
            )
            entity_type = "violation"
        else:
            payload.setdefault("check_in_at", event.captured_at.isoformat())
            obj, created = await contractor_svc.log_attendance(
                session, principal, AttendanceCreate.model_validate(payload), source="mobile"
            )
            entity_type = "attendance"
    except ValidationError as exc:
        INGEST_EVENTS.labels(event.event_type, "invalid").inc()
        raise ValueError(f"invalid payload: {exc.errors()[:3]}") from exc
    except AppError as exc:
        INGEST_EVENTS.labels(event.event_type, "rejected").inc()
        raise ValueError(exc.detail) from exc
    INGEST_EVENTS.labels(event.event_type, "created" if created else "duplicate").inc()
    return ("accepted" if created else "duplicate"), entity_type, str(obj.id)
