"""Tamper-evident audit trail (FR15).

Each entry's hash = SHA-256(prev_hash || canonical_json(entry)). Appends are
serialised with a Postgres advisory lock so the chain is strictly linear; the
table is write-once (UPDATE/DELETE rejected by a trigger, see migrations).
Any modification of a historical row breaks every subsequent hash.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import chain_hash
from app.models import AuditLog

GENESIS_HASH = "0" * 64
_LOCK_KEY = 0x434D47_41554454  # "CMG" "AUDT"


def hash_payload(
    *, event_id: str, entity_type: str, entity_id: str, action: str, actor_id: str | None,
    before: Any, after: Any, ts: datetime,
) -> dict[str, Any]:
    return {
        "event_id": event_id,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "action": action,
        "actor_id": actor_id,
        "before": before,
        "after": after,
        "ts": ts.astimezone(UTC).isoformat(),
    }


async def append(session: AsyncSession, envelope: dict[str, Any]) -> AuditLog | None:
    """Append a domain event to the chain. Idempotent on event_id. Caller commits."""
    await session.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": _LOCK_KEY})
    event_id = uuid.UUID(envelope["event_id"])
    if (await session.execute(select(AuditLog.id).where(AuditLog.event_id == event_id))).first():
        return None
    prev = (
        await session.execute(select(AuditLog.hash).order_by(AuditLog.id.desc()).limit(1))
    ).scalar_one_or_none() or GENESIS_HASH
    ts = datetime.fromisoformat(envelope["occurred_at"])
    actor = envelope.get("actor") or {}
    before = envelope.get("before")
    after = envelope.get("after")
    if after is None and envelope.get("data"):
        after = {"data": envelope["data"]}
    payload = hash_payload(
        event_id=str(event_id),
        entity_type=envelope["entity_type"],
        entity_id=envelope["entity_id"],
        action=envelope["event_type"],
        actor_id=actor.get("id"),
        before=before,
        after=after,
        ts=ts,
    )
    entry = AuditLog(
        event_id=event_id,
        entity_type=envelope["entity_type"],
        entity_id=envelope["entity_id"],
        action=envelope["event_type"],
        actor_id=uuid.UUID(actor["id"]) if actor.get("id") else None,
        actor_name=actor.get("name"),
        mine_id=uuid.UUID(envelope["mine_id"]) if envelope.get("mine_id") else None,
        subsidiary_id=uuid.UUID(envelope["subsidiary_id"]) if envelope.get("subsidiary_id") else None,
        before=before,
        after=after,
        ts=ts,
        prev_hash=prev,
        hash=chain_hash(prev, payload),
    )
    session.add(entry)
    await session.flush()
    return entry


async def verify_chain(session: AsyncSession, batch: int = 2000) -> dict[str, Any]:
    prev = GENESIS_HASH
    checked = 0
    last_id = 0
    while True:
        rows = (
            await session.execute(
                select(AuditLog).where(AuditLog.id > last_id).order_by(AuditLog.id).limit(batch)
            )
        ).scalars().all()
        if not rows:
            break
        for row in rows:
            payload = hash_payload(
                event_id=str(row.event_id), entity_type=row.entity_type, entity_id=row.entity_id,
                action=row.action, actor_id=str(row.actor_id) if row.actor_id else None,
                before=row.before, after=row.after, ts=row.ts,
            )
            if row.prev_hash != prev or chain_hash(prev, payload) != row.hash:
                return {"valid": False, "checked": checked, "first_invalid_id": row.id, "head_hash": prev,
                        "verified_at": datetime.now(UTC)}
            prev = row.hash
            checked += 1
            last_id = row.id
        session.expunge_all()
    return {"valid": True, "checked": checked, "first_invalid_id": None, "head_hash": prev,
            "verified_at": datetime.now(UTC)}


async def chain_length(session: AsyncSession) -> int:
    return int((await session.execute(select(func.count()).select_from(AuditLog))).scalar_one())
