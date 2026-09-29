"""Inspections with geo-tagging, photo evidence and idempotent offline submission (FR4)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Select, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import InvalidState, NotFound
from app.models import Inspection, Violation
from app.models.base import snapshot
from app.models.enums import InspectionOutcome, InspectionStatus, InspectionType
from app.schemas.field import InspectionCreate, InspectionReview
from app.services import geo
from app.services.access import Perm, Principal, assert_mine_access, scope_mines
from app.services.events import record_event

AUDIT_FIELDS = (
    "number", "inspection_type", "title", "outcome", "status", "latitude", "longitude",
    "geo_verified", "distance_from_mine_km", "inspected_at", "source",
)


def base_query(principal: Principal) -> Select[Any]:
    return scope_mines(select(Inspection), principal, Inspection.mine_id)


def _outcome_from_checklist(checklist: list[dict[str, Any]]) -> InspectionOutcome:
    if not checklist:
        return InspectionOutcome.PENDING
    failed = sum(1 for c in checklist if not c.get("passed"))
    if failed == 0:
        return InspectionOutcome.COMPLIANT
    return InspectionOutcome.MINOR_ISSUES if failed / len(checklist) <= 0.2 else InspectionOutcome.NON_COMPLIANT


async def list_inspections(
    session: AsyncSession,
    principal: Principal,
    *,
    mine_id: uuid.UUID | None,
    outcome: InspectionOutcome | None,
    inspection_type: InspectionType | None,
    q: str | None,
    date_from: datetime | None,
    date_to: datetime | None,
    offset: int,
    limit: int,
) -> tuple[list[Inspection], int]:
    stmt = base_query(principal)
    if mine_id:
        stmt = stmt.where(Inspection.mine_id == mine_id)
    if outcome:
        stmt = stmt.where(Inspection.outcome == outcome)
    if inspection_type:
        stmt = stmt.where(Inspection.inspection_type == inspection_type)
    if date_from:
        stmt = stmt.where(Inspection.inspected_at >= date_from)
    if date_to:
        stmt = stmt.where(Inspection.inspected_at <= date_to)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(Inspection.title.ilike(like), Inspection.notes.ilike(like)))
    total = (await session.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    rows = (
        await session.execute(stmt.order_by(Inspection.inspected_at.desc()).offset(offset).limit(limit))
    ).scalars().unique().all()
    return list(rows), int(total)


async def get_inspection(session: AsyncSession, principal: Principal, inspection_id: uuid.UUID) -> Inspection:
    row = (await session.execute(base_query(principal).where(Inspection.id == inspection_id))).scalars().first()
    if row is None:
        raise NotFound("Inspection not found")
    return row


async def find_by_client_event(session: AsyncSession, client_event_id: str) -> Inspection | None:
    return (
        await session.execute(select(Inspection).where(Inspection.client_event_id == client_event_id))
    ).scalars().first()


async def create_inspection(
    session: AsyncSession,
    principal: Principal,
    data: InspectionCreate,
    *,
    source: str = "web",
    commit: bool = True,
) -> tuple[Inspection, bool]:
    """Returns (inspection, created). Replays of the same client_event_id are no-ops."""
    principal.require(Perm.INSPECTION_WRITE)
    if data.client_event_id:
        existing = await find_by_client_event(session, data.client_event_id)
        if existing:
            return existing, False
    mine = await assert_mine_access(session, principal, data.mine_id, write=True)
    lat = data.geo.latitude if data.geo else None
    lon = data.geo.longitude if data.geo else None
    verified, distance = geo.verify_location(
        lat, lon, mine.latitude, mine.longitude, mine.boundary_geojson, get_settings().geofence_radius_km
    )
    checklist = [c.model_dump() for c in data.checklist]
    inspection = Inspection(
        mine_id=mine.id,
        inspector_id=principal.id,
        inspection_type=data.inspection_type,
        title=data.title,
        notes=data.notes,
        checklist=checklist,
        latitude=lat,
        longitude=lon,
        geo_accuracy_m=data.geo.accuracy_m if data.geo else None,
        distance_from_mine_km=distance,
        geo_verified=verified,
        inspected_at=data.inspected_at or datetime.now(UTC),
        outcome=data.outcome or _outcome_from_checklist(checklist),
        status=InspectionStatus.SUBMITTED,
        client_event_id=data.client_event_id,
        source=source,
    )
    session.add(inspection)
    await session.flush()
    record_event(
        session, "inspection.submitted", entity_type="inspection", entity_id=inspection.id, actor=principal,
        mine_id=mine.id, subsidiary_id=mine.subsidiary_id, after=snapshot(inspection, AUDIT_FIELDS),
        data={"geo_verified": verified, "distance_km": distance, "source": source},
    )
    if lat is not None and not verified:
        record_event(
            session, "inspection.geofence_mismatch", entity_type="inspection", entity_id=inspection.id,
            actor=principal, mine_id=mine.id, subsidiary_id=mine.subsidiary_id,
            data={"distance_km": distance, "radius_km": get_settings().geofence_radius_km},
        )
    if commit:
        await session.commit()
    return inspection, True


async def review_inspection(
    session: AsyncSession, principal: Principal, inspection_id: uuid.UUID, data: InspectionReview
) -> Inspection:
    principal.require(Perm.VIOLATION_CONFIRM)
    inspection = await get_inspection(session, principal, inspection_id)
    await assert_mine_access(session, principal, inspection.mine_id, write=True)
    if inspection.status == InspectionStatus.REVIEWED:
        raise InvalidState("Inspection already reviewed")
    before = snapshot(inspection, AUDIT_FIELDS)
    inspection.outcome = data.outcome
    inspection.status = InspectionStatus.REVIEWED
    if data.notes:
        inspection.notes = f"{inspection.notes}\n\n[Review by {principal.full_name}] {data.notes}".strip()
    record_event(
        session, "inspection.reviewed", entity_type="inspection", entity_id=inspection.id, actor=principal,
        mine_id=inspection.mine_id, subsidiary_id=inspection.mine.subsidiary_id, before=before,
        after=snapshot(inspection, AUDIT_FIELDS),
    )
    await session.commit()
    return inspection


async def violations_for(session: AsyncSession, inspection_id: uuid.UUID) -> list[Violation]:
    return list(
        (
            await session.execute(
                select(Violation).where(Violation.inspection_id == inspection_id).order_by(Violation.created_at)
            )
        ).scalars().unique().all()
    )
