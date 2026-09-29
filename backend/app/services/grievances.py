"""Grievance redressal: raise → assign → resolve → close/reopen, under a resolution SLA.

Anyone who works at a mine (officials, corporate staff, contractors) can raise a
grievance, optionally anonymously. Managers of that mine assign and resolve it; the
person who raised it confirms the fix (with a satisfaction rating) or reopens it.
A Temporal workflow escalates anything still open past its SLA.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import Select, and_, case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import Forbidden, InvalidState, NotFound
from app.models import Grievance, User
from app.models.base import snapshot
from app.models.enums import GrievanceCategory, GrievanceStatus, Role, Severity, UserStatus
from app.schemas.grievance import (
    GrievanceAssign,
    GrievanceClose,
    GrievanceCreate,
    GrievanceOut,
    GrievanceReject,
    GrievanceReopen,
    GrievanceResolve,
)
from app.services.access import Perm, Principal, assert_mine_access, scope_mines
from app.services.events import record_event

G_FIELDS = (
    "number", "category", "subject", "priority", "status", "assigned_to", "due_at", "escalation_level",
    "resolution_notes", "resolved_at", "closed_at", "satisfaction", "reopen_count", "is_anonymous",
)

# Resolution SLA by priority. Grievances that affect safety are handled fastest.
SLA_HOURS = {Severity.CRITICAL: 24, Severity.HIGH: 72, Severity.MEDIUM: 168, Severity.LOW: 360}
ACTIVE = (GrievanceStatus.OPEN, GrievanceStatus.ASSIGNED, GrievanceStatus.IN_PROGRESS)
MAX_REOPENS = 3


def workflow_id(grievance_id: uuid.UUID | str) -> str:
    return f"grievance-sla-{grievance_id}"


def sla_due(priority: Severity, start: datetime) -> datetime:
    return start + timedelta(hours=SLA_HOURS[priority])


def base_query(principal: Principal) -> Select[Any]:
    stmt = select(Grievance)
    if principal.role == Role.CONTRACTOR:
        # Contractors see what they raised and grievances filed against their own firm.
        own = Grievance.raised_by == principal.id
        firm = and_(Grievance.contractor_id.is_not(None), Grievance.contractor_id == principal.contractor_id)
        return stmt.where(or_(own, firm))
    if principal.is_global:
        return stmt
    # Everyone else sees their mine scope plus anything they raised themselves.
    scoped_ids = scope_mines(select(Grievance.id), principal, Grievance.mine_id)
    return stmt.where(or_(Grievance.raised_by == principal.id, Grievance.id.in_(scoped_ids)))


def can_manage(principal: Principal) -> bool:
    return principal.can(Perm.GRIEVANCE_MANAGE)


def to_out(g: Grievance, principal: Principal) -> GrievanceOut:
    out = GrievanceOut.model_validate(g)
    mine = g.raised_by == principal.id
    if g.is_anonymous and not mine and principal.role != Role.ADMIN:
        out.raiser = None
    out.is_mine = mine
    out.can_manage = can_manage(principal)
    return out


async def list_grievances(
    session: AsyncSession,
    principal: Principal,
    *,
    view: str,
    status: GrievanceStatus | None,
    category: GrievanceCategory | None,
    mine_id: uuid.UUID | None,
    overdue: bool,
    q: str | None,
    offset: int,
    limit: int,
) -> tuple[list[Grievance], int]:
    stmt = base_query(principal)
    if view == "raised":
        stmt = stmt.where(Grievance.raised_by == principal.id)
    elif view == "assigned":
        stmt = stmt.where(Grievance.assigned_to == principal.id)
    if status:
        stmt = stmt.where(Grievance.status == status)
    if category:
        stmt = stmt.where(Grievance.category == category)
    if mine_id:
        stmt = stmt.where(Grievance.mine_id == mine_id)
    if overdue:
        stmt = stmt.where(Grievance.status.in_(ACTIVE), Grievance.due_at < datetime.now(UTC))
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(Grievance.subject.ilike(like))
    total = (await session.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    priority_rank = case(
        (Grievance.priority == Severity.CRITICAL, 0), (Grievance.priority == Severity.HIGH, 1),
        (Grievance.priority == Severity.MEDIUM, 2), else_=3,
    )
    active_first = case((Grievance.status.in_(ACTIVE), 0), else_=1)
    rows = (
        await session.execute(
            stmt.order_by(active_first, priority_rank, Grievance.due_at.desc()).offset(offset).limit(limit)
        )
    ).scalars().unique().all()
    return list(rows), int(total)


async def get_grievance(session: AsyncSession, principal: Principal, grievance_id: uuid.UUID) -> Grievance:
    g = (await session.execute(base_query(principal).where(Grievance.id == grievance_id))).scalars().first()
    if g is None:
        raise NotFound("Grievance not found")
    return g


def _event(session: AsyncSession, g: Grievance, event: str, actor: Principal | None, before: dict | None,
           **data: Any) -> None:
    record_event(
        session, f"grievance.{event}", entity_type="grievance", entity_id=g.id,
        # Anonymous grievances never put the raiser's identity on the (widely readable) audit trail.
        actor=None if (g.is_anonymous and actor and actor.id == g.raised_by) else actor,
        mine_id=g.mine_id, subsidiary_id=g.mine.subsidiary_id, before=before, after=snapshot(g, G_FIELDS),
        data={"number": g.number, "subject": g.subject, "priority": g.priority.value,
              "category": g.category.value, "raiser_id": str(g.raised_by) if g.raised_by else None,
              "assignee_id": str(g.assigned_to) if g.assigned_to else None,
              "mine_name": g.mine.name, **data},
    )


async def create_grievance(session: AsyncSession, principal: Principal, data: GrievanceCreate) -> Grievance:
    principal.require(Perm.GRIEVANCE_RAISE)
    mine = await assert_mine_access(session, principal, data.mine_id, write=True)
    now = datetime.now(UTC)
    g = Grievance(
        mine_id=mine.id,
        raised_by=principal.id,
        contractor_id=principal.contractor_id if principal.role == Role.CONTRACTOR else None,
        is_anonymous=data.is_anonymous,
        category=data.category,
        subject=data.subject,
        description=data.description,
        priority=data.priority,
        status=GrievanceStatus.OPEN,
        due_at=sla_due(data.priority, now),
    )
    session.add(g)
    await session.flush()
    await session.refresh(g, ["mine"])
    _event(session, g, "raised", principal, None)
    await session.commit()
    return await get_grievance(session, principal, g.id)


async def _load_for_manage(session: AsyncSession, principal: Principal, grievance_id: uuid.UUID) -> Grievance:
    principal.require(Perm.GRIEVANCE_MANAGE)
    g = await get_grievance(session, principal, grievance_id)
    await assert_mine_access(session, principal, g.mine_id, write=True)
    return g


async def assign(session: AsyncSession, principal: Principal, grievance_id: uuid.UUID,
                 data: GrievanceAssign) -> Grievance:
    g = await _load_for_manage(session, principal, grievance_id)
    if g.status not in ACTIVE:
        raise InvalidState(f"A {g.status.value} grievance cannot be assigned")
    assignee = await session.get(User, data.assignee_id)
    if assignee is None or assignee.status != UserStatus.ACTIVE:
        raise NotFound("Assignee not found")
    if assignee.role not in (Role.MINE_OFFICIAL, Role.CORPORATE, Role.ADMIN):
        raise InvalidState("Grievances can only be assigned to mine officials, corporate staff or administrators")
    if assignee.role == Role.MINE_OFFICIAL and assignee.mine_id != g.mine_id:
        raise InvalidState("The assignee must work at the grievance's mine")
    if g.raised_by and assignee.id == g.raised_by:
        raise InvalidState("A grievance cannot be assigned to the person who raised it")
    before = snapshot(g, G_FIELDS)
    g.assigned_to = assignee.id
    if data.priority and data.priority != g.priority:
        g.priority = data.priority
        g.due_at = sla_due(data.priority, g.created_at)
    if g.status == GrievanceStatus.OPEN:
        g.status = GrievanceStatus.ASSIGNED
    _event(session, g, "assigned", principal, before, note=data.note)
    await session.commit()
    return await get_grievance(session, principal, g.id)


async def start(session: AsyncSession, principal: Principal, grievance_id: uuid.UUID) -> Grievance:
    g = await get_grievance(session, principal, grievance_id)
    if g.assigned_to != principal.id and not can_manage(principal):
        raise Forbidden("Only the assignee or a manager can start work on this grievance")
    if g.status not in (GrievanceStatus.OPEN, GrievanceStatus.ASSIGNED):
        raise InvalidState(f"A {g.status.value} grievance cannot be started")
    before = snapshot(g, G_FIELDS)
    g.status = GrievanceStatus.IN_PROGRESS
    _event(session, g, "started", principal, before)
    await session.commit()
    return await get_grievance(session, principal, g.id)


async def resolve(session: AsyncSession, principal: Principal, grievance_id: uuid.UUID,
                  data: GrievanceResolve) -> Grievance:
    g = await get_grievance(session, principal, grievance_id)
    if g.assigned_to != principal.id:
        g = await _load_for_manage(session, principal, grievance_id)
    if g.status not in ACTIVE:
        raise InvalidState(f"A {g.status.value} grievance cannot be resolved")
    if g.raised_by == principal.id:
        raise Forbidden("You cannot resolve a grievance you raised yourself")
    before = snapshot(g, G_FIELDS)
    g.status = GrievanceStatus.RESOLVED
    g.resolution_notes = data.resolution_notes
    g.resolved_at = datetime.now(UTC)
    g.resolved_by = principal.id
    _event(session, g, "resolved", principal, before)
    await session.commit()
    return await get_grievance(session, principal, g.id)


async def reject(session: AsyncSession, principal: Principal, grievance_id: uuid.UUID,
                 data: GrievanceReject) -> Grievance:
    g = await _load_for_manage(session, principal, grievance_id)
    if g.status not in ACTIVE:
        raise InvalidState(f"A {g.status.value} grievance cannot be rejected")
    if g.raised_by == principal.id:
        raise Forbidden("You cannot reject a grievance you raised yourself")
    before = snapshot(g, G_FIELDS)
    g.status = GrievanceStatus.REJECTED
    g.resolution_notes = data.reason
    g.resolved_at = datetime.now(UTC)
    g.resolved_by = principal.id
    _event(session, g, "rejected", principal, before)
    await session.commit()
    return await get_grievance(session, principal, g.id)


async def close(session: AsyncSession, principal: Principal, grievance_id: uuid.UUID,
                data: GrievanceClose) -> Grievance:
    g = await get_grievance(session, principal, grievance_id)
    if g.raised_by != principal.id:
        raise Forbidden("Only the person who raised the grievance can confirm and close it")
    if g.status != GrievanceStatus.RESOLVED:
        raise InvalidState("Only a resolved grievance can be closed")
    before = snapshot(g, G_FIELDS)
    g.status = GrievanceStatus.CLOSED
    g.satisfaction = data.satisfaction
    g.closed_at = datetime.now(UTC)
    _event(session, g, "closed", principal, before, comment=data.comment)
    await session.commit()
    return await get_grievance(session, principal, g.id)


async def reopen(session: AsyncSession, principal: Principal, grievance_id: uuid.UUID,
                 data: GrievanceReopen) -> Grievance:
    g = await get_grievance(session, principal, grievance_id)
    if g.raised_by != principal.id:
        raise Forbidden("Only the person who raised the grievance can reopen it")
    if g.status not in (GrievanceStatus.RESOLVED, GrievanceStatus.REJECTED):
        raise InvalidState("Only a resolved or rejected grievance can be reopened")
    if g.reopen_count >= MAX_REOPENS:
        raise InvalidState(f"This grievance has already been reopened {MAX_REOPENS} times; raise a new one")
    before = snapshot(g, G_FIELDS)
    now = datetime.now(UTC)
    g.status = GrievanceStatus.ASSIGNED if g.assigned_to else GrievanceStatus.OPEN
    g.reopen_count += 1
    g.resolved_at = None
    g.resolved_by = None
    g.due_at = sla_due(g.priority, now)
    _event(session, g, "reopened", principal, before, reason=data.reason)
    await session.commit()
    return await get_grievance(session, principal, g.id)


async def escalate_if_overdue(session: AsyncSession, grievance_id: uuid.UUID, max_level: int) -> dict[str, Any]:
    """Workflow step: bump the escalation level of an overdue grievance and give it a fresh window."""
    g = await session.get(Grievance, grievance_id)
    if g is None:
        return {"exists": False}
    now = datetime.now(UTC)
    escalated = False
    if g.status in ACTIVE and g.due_at <= now:
        escalated = True
        before = snapshot(g, G_FIELDS)
        g.escalation_level = min(g.escalation_level + 1, max_level)
        # Each level gets half the original window to act before moving further up.
        g.due_at = now + timedelta(hours=max(SLA_HOURS[g.priority] // 2, 12))
        target = {1: "mine_management", 2: "subsidiary_corporate"}.get(g.escalation_level, "headquarters")
        _event(session, g, "escalated", None, before, level=g.escalation_level, target=target)
    return {"exists": True, "status": g.status.value, "due_at": g.due_at.isoformat(),
            "level": g.escalation_level, "escalated": escalated}


async def summary(session: AsyncSession, principal: Principal, mine_id: uuid.UUID | None) -> dict[str, Any]:
    ids = base_query(principal).with_only_columns(Grievance.id)
    if mine_id:
        ids = ids.where(Grievance.mine_id == mine_id)
    stmt = select(Grievance.status, Grievance.category, Grievance.due_at, Grievance.created_at,
                  Grievance.resolved_at, Grievance.satisfaction).where(Grievance.id.in_(ids))
    rows = (await session.execute(stmt)).all()
    now = datetime.now(UTC)
    by_status = {s.value: 0 for s in GrievanceStatus}
    by_category = {c.value: 0 for c in GrievanceCategory}
    overdue = 0
    hours: list[float] = []
    ratings: list[int] = []
    for status, category, due_at, created_at, resolved_at, satisfaction in rows:
        by_status[status.value] += 1
        by_category[category.value] += 1
        if status in ACTIVE and due_at < now:
            overdue += 1
        if resolved_at and status in (GrievanceStatus.RESOLVED, GrievanceStatus.CLOSED):
            hours.append((resolved_at - created_at).total_seconds() / 3600)
        if satisfaction:
            ratings.append(satisfaction)
    return {
        "total": len(rows),
        "open": sum(by_status[s.value] for s in ACTIVE),
        "overdue": overdue,
        "resolved": by_status["resolved"],
        "closed": by_status["closed"],
        "avg_resolution_hours": round(sum(hours) / len(hours), 1) if hours else None,
        "avg_satisfaction": round(sum(ratings) / len(ratings), 2) if ratings else None,
        "by_category": by_category,
        "by_status": by_status,
    }
