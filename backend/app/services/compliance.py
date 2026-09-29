"""Statutory compliance management (FR1–FR3)."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import Select, and_, case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import InvalidState, NotFound
from app.models import ComplianceItem, Document, Regulation, User
from app.models.base import snapshot
from app.models.enums import ComplianceCategory, ComplianceStatus, Frequency
from app.schemas.compliance import ComplianceComplete, ComplianceCreate, ComplianceUpdate
from app.services.access import Perm, Principal, assert_mine_access, scope_mines
from app.services.events import record_event

AUDIT_FIELDS = (
    "title", "category", "regulation_ref", "frequency", "due_date", "status", "owner_id",
    "last_completed_at", "completion_notes", "escalated",
)

_FREQ_MONTHS = {
    Frequency.MONTHLY: 1,
    Frequency.QUARTERLY: 3,
    Frequency.HALF_YEARLY: 6,
    Frequency.ANNUAL: 12,
}


def add_months(d: date, months: int) -> date:
    month = d.month - 1 + months
    year = d.year + month // 12
    month = month % 12 + 1
    days_in_month = [31, 29 if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0) else 28,
                     31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month - 1]
    return date(year, month, min(d.day, days_in_month))


def next_due_date(current_due: date, frequency: Frequency, today: date) -> date | None:
    months = _FREQ_MONTHS.get(frequency)
    if months is None:
        return None
    nxt = add_months(current_due, months)
    while nxt <= today:
        nxt = add_months(nxt, months)
    return nxt


def derive_status(item: ComplianceItem, today: date) -> ComplianceStatus:
    """Time-based status transitions (violated/compliant/in-progress are set explicitly)."""
    if item.status in (ComplianceStatus.COMPLIANT, ComplianceStatus.VIOLATED):
        return item.status
    if item.due_date < today:
        return ComplianceStatus.OVERDUE
    return item.status if item.status == ComplianceStatus.IN_PROGRESS else ComplianceStatus.DUE


def base_query(principal: Principal) -> Select[Any]:
    return scope_mines(select(ComplianceItem), principal, ComplianceItem.mine_id)


async def list_items(
    session: AsyncSession,
    principal: Principal,
    *,
    mine_id: uuid.UUID | None,
    category: ComplianceCategory | None,
    status: ComplianceStatus | None,
    due_before: date | None,
    q: str | None,
    offset: int,
    limit: int,
) -> tuple[list[ComplianceItem], int]:
    stmt = base_query(principal)
    if mine_id:
        stmt = stmt.where(ComplianceItem.mine_id == mine_id)
    if category:
        stmt = stmt.where(ComplianceItem.category == category)
    if status:
        stmt = stmt.where(ComplianceItem.status == status)
    if due_before:
        stmt = stmt.where(ComplianceItem.due_date <= due_before)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(ComplianceItem.title.ilike(like), ComplianceItem.regulation_ref.ilike(like)))
    total = (await session.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    rows = (
        await session.execute(
            stmt.order_by(
                case((ComplianceItem.status == ComplianceStatus.OVERDUE, 0), else_=1),
                ComplianceItem.due_date,
            ).offset(offset).limit(limit)
        )
    ).scalars().unique().all()
    return list(rows), int(total)


async def get_item(session: AsyncSession, principal: Principal, item_id: uuid.UUID) -> ComplianceItem:
    item = (
        await session.execute(base_query(principal).where(ComplianceItem.id == item_id))
    ).scalars().first()
    if item is None:
        raise NotFound("Compliance item not found")
    return item


async def create_item(session: AsyncSession, principal: Principal, data: ComplianceCreate) -> ComplianceItem:
    principal.require(Perm.COMPLIANCE_WRITE)
    mine = await assert_mine_access(session, principal, data.mine_id, write=True)
    regulation_ref = data.regulation_ref
    if data.regulation_id:
        reg = await session.get(Regulation, data.regulation_id)
        if reg is None:
            raise NotFound("Regulation not found")
        regulation_ref = regulation_ref or f"{reg.act} — {reg.section or reg.code}"
    if data.owner_id and await session.get(User, data.owner_id) is None:
        raise NotFound("Owner not found")
    item = ComplianceItem(
        mine_id=data.mine_id,
        category=data.category,
        title=data.title,
        description=data.description,
        regulation_id=data.regulation_id,
        regulation_ref=regulation_ref,
        frequency=data.frequency,
        due_date=data.due_date,
        owner_id=data.owner_id,
        created_by=principal.id,
    )
    item.status = derive_status(item, datetime.now(UTC).date())
    session.add(item)
    await session.flush()
    record_event(
        session, "compliance.created", entity_type="compliance_item", entity_id=item.id, actor=principal,
        mine_id=mine.id, subsidiary_id=mine.subsidiary_id, after=snapshot(item, AUDIT_FIELDS),
    )
    await session.commit()
    return await get_item(session, principal, item.id)


async def update_item(
    session: AsyncSession, principal: Principal, item_id: uuid.UUID, data: ComplianceUpdate
) -> ComplianceItem:
    principal.require(Perm.COMPLIANCE_WRITE)
    item = await get_item(session, principal, item_id)
    await assert_mine_access(session, principal, item.mine_id, write=True)
    before = snapshot(item, AUDIT_FIELDS)
    changes = data.model_dump(exclude_unset=True)
    for key, value in changes.items():
        setattr(item, key, value)
    if "status" not in changes:
        item.status = derive_status(item, datetime.now(UTC).date())
    record_event(
        session, "compliance.updated", entity_type="compliance_item", entity_id=item.id, actor=principal,
        mine_id=item.mine_id, subsidiary_id=item.mine.subsidiary_id, before=before,
        after=snapshot(item, AUDIT_FIELDS), data={"due_date_changed": "due_date" in changes},
    )
    await session.commit()
    return await get_item(session, principal, item.id)


async def complete_item(
    session: AsyncSession, principal: Principal, item_id: uuid.UUID, data: ComplianceComplete
) -> ComplianceItem:
    principal.require(Perm.COMPLIANCE_WRITE)
    item = await get_item(session, principal, item_id)
    await assert_mine_access(session, principal, item.mine_id, write=True)
    if data.evidence_document_id and await session.get(Document, data.evidence_document_id) is None:
        raise NotFound("Evidence document not found")
    before = snapshot(item, AUDIT_FIELDS)
    now = datetime.now(UTC)
    item.last_completed_at = now
    item.last_completed_by = principal.id
    item.completion_notes = data.notes
    item.evidence_document_id = data.evidence_document_id
    item.escalated = False
    nxt = next_due_date(item.due_date, item.frequency, now.date())
    if nxt:
        # Recurring obligation: roll forward to the next statutory period.
        item.due_date = nxt
        item.status = ComplianceStatus.DUE
    else:
        item.status = ComplianceStatus.COMPLIANT
    record_event(
        session, "compliance.completed", entity_type="compliance_item", entity_id=item.id, actor=principal,
        mine_id=item.mine_id, subsidiary_id=item.mine.subsidiary_id, before=before,
        after=snapshot(item, AUDIT_FIELDS), data={"rolled_forward_to": nxt.isoformat() if nxt else None},
    )
    await session.commit()
    return await get_item(session, principal, item.id)


async def delete_item(session: AsyncSession, principal: Principal, item_id: uuid.UUID) -> None:
    principal.require(Perm.COMPLIANCE_WRITE)
    item = await get_item(session, principal, item_id)
    await assert_mine_access(session, principal, item.mine_id, write=True)
    if item.status == ComplianceStatus.VIOLATED:
        raise InvalidState("Violated items are retained for the statutory record and cannot be deleted")
    record_event(
        session, "compliance.deleted", entity_type="compliance_item", entity_id=item.id, actor=principal,
        mine_id=item.mine_id, subsidiary_id=item.mine.subsidiary_id, before=snapshot(item, AUDIT_FIELDS),
    )
    await session.delete(item)
    await session.commit()


async def summary(session: AsyncSession, principal: Principal, mine_id: uuid.UUID | None = None) -> dict[str, Any]:
    stmt = scope_mines(
        select(ComplianceItem.category, ComplianceItem.status, func.count()).group_by(
            ComplianceItem.category, ComplianceItem.status
        ),
        principal,
        ComplianceItem.mine_id,
    )
    if mine_id:
        stmt = stmt.where(ComplianceItem.mine_id == mine_id)
    rows = (await session.execute(stmt)).all()
    by_status = {s.value: 0 for s in ComplianceStatus}
    by_category: dict[str, dict[str, int]] = {c.value: {s.value: 0 for s in ComplianceStatus} for c in ComplianceCategory}
    for category, status, count in rows:
        by_status[status.value] += count
        by_category[category.value][status.value] += count
    total = sum(by_status.values())
    rate = round(100.0 * by_status["compliant"] / total, 1) if total else 100.0
    # Items not yet due are on schedule and count as compliant in the overview;
    # overdue + violated are non-compliant.
    on_track = by_status["compliant"] + by_status["due"]
    return {
        "overview": {
            "compliant": on_track,
            "in_progress": by_status["in_progress"],
            "non_compliant": by_status["overdue"] + by_status["violated"],
        },
        "total": total,
        "compliant": by_status["compliant"],
        "in_progress": by_status["in_progress"],
        "due": by_status["due"],
        "overdue": by_status["overdue"],
        "violated": by_status["violated"],
        "compliance_rate": round(100.0 * on_track / total, 1) if total else 100.0,
        "strict_compliance_rate": rate,
        "by_category": by_category,
    }


async def refresh_statuses(session: AsyncSession, today: date | None = None) -> list[ComplianceItem]:
    """Daily sweep: move past-due items to OVERDUE. Returns items that newly became overdue."""
    today = today or datetime.now(UTC).date()
    rows = (
        await session.execute(
            select(ComplianceItem).where(
                and_(
                    ComplianceItem.due_date < today,
                    ComplianceItem.status.in_([ComplianceStatus.DUE, ComplianceStatus.IN_PROGRESS]),
                )
            )
        )
    ).scalars().unique().all()
    changed = []
    for item in rows:
        before = snapshot(item, AUDIT_FIELDS)
        item.status = ComplianceStatus.OVERDUE
        record_event(
            session, "compliance.overdue", entity_type="compliance_item", entity_id=item.id, actor=None,
            mine_id=item.mine_id, subsidiary_id=item.mine.subsidiary_id, before=before,
            after=snapshot(item, AUDIT_FIELDS),
        )
        changed.append(item)
    return changed


def upcoming_window(days: int = 30) -> tuple[date, date]:
    today = datetime.now(UTC).date()
    return today, today + timedelta(days=days)
