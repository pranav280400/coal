"""Violations (FR5) and the corrective-action lifecycle (FR6).

Lifecycle: open → action_assigned → pending_verification → closed, with
escalation driven by the Temporal ``ViolationEscalationWorkflow`` which is
signalled on every transition below.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Select, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai import classifier
from app.core.errors import Forbidden, InvalidState, NotFound
from app.models import Contractor, CorrectiveAction, Inspection, User, Violation
from app.models.base import snapshot
from app.models.enums import (
    ActionStatus,
    ComplianceCategory,
    DetectedBy,
    Role,
    Severity,
    UserStatus,
    ViolationKind,
    ViolationStatus,
)
from app.schemas.field import ActionCreate, ActionSubmit, ActionVerify, ViolationConfirm, ViolationCreate
from app.services.access import Perm, Principal, assert_mine_access, scope_mines, visible_mine_ids
from app.services.events import record_event
from app.workflows import client as temporal

V_FIELDS = (
    "number", "kind", "category", "title", "severity", "severity_confirmed", "ai_suggested_severity",
    "status", "escalation_level", "contractor_id", "closed_at",
)
A_FIELDS = ("title", "assigned_to", "deadline", "status", "submitted_at", "verified_at", "verification_notes")


def escalation_workflow_id(violation_id: uuid.UUID | str) -> str:
    return f"violation-escalation-{violation_id}"


def base_query(principal: Principal) -> Select[Any]:
    stmt = scope_mines(select(Violation), principal, Violation.mine_id)
    if principal.role == Role.CONTRACTOR:
        stmt = stmt.where(Violation.contractor_id == principal.contractor_id)
    return stmt


async def list_violations(
    session: AsyncSession,
    principal: Principal,
    *,
    mine_id: uuid.UUID | None,
    status: ViolationStatus | None,
    severity: Severity | None,
    category: ComplianceCategory | None,
    contractor_id: uuid.UUID | None,
    kind: ViolationKind | None,
    q: str | None,
    open_only: bool,
    offset: int,
    limit: int,
) -> tuple[list[Violation], int]:
    stmt = base_query(principal)
    if mine_id:
        stmt = stmt.where(Violation.mine_id == mine_id)
    if status:
        stmt = stmt.where(Violation.status == status)
    if open_only:
        stmt = stmt.where(Violation.status != ViolationStatus.CLOSED)
    if severity:
        stmt = stmt.where(Violation.severity == severity)
    if category:
        stmt = stmt.where(Violation.category == category)
    if contractor_id:
        stmt = stmt.where(Violation.contractor_id == contractor_id)
    if kind:
        stmt = stmt.where(Violation.kind == kind)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(Violation.title.ilike(like), Violation.description.ilike(like)))
    total = (await session.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    rows = (
        await session.execute(stmt.order_by(Violation.occurred_at.desc()).offset(offset).limit(limit))
    ).scalars().unique().all()
    return list(rows), int(total)


async def get_violation(session: AsyncSession, principal: Principal, violation_id: uuid.UUID) -> Violation:
    row = (await session.execute(base_query(principal).where(Violation.id == violation_id))).scalars().first()
    if row is None:
        raise NotFound("Violation not found")
    return row


async def create_violation(
    session: AsyncSession,
    principal: Principal,
    data: ViolationCreate,
    *,
    detected_by: DetectedBy = DetectedBy.HUMAN,
    commit: bool = True,
) -> tuple[Violation, bool]:
    principal.require(Perm.VIOLATION_WRITE)
    if data.client_event_id:
        existing = (
            await session.execute(select(Violation).where(Violation.client_event_id == data.client_event_id))
        ).scalars().first()
        if existing:
            return existing, False
    mine = await assert_mine_access(session, principal, data.mine_id, write=True)
    if data.inspection_id:
        insp = await session.get(Inspection, data.inspection_id)
        if insp is None or insp.mine_id != mine.id:
            raise InvalidState("Inspection does not belong to this mine")
    contractor_id = data.contractor_id
    if principal.role == Role.CONTRACTOR:
        contractor_id = principal.contractor_id
    if contractor_id and await session.get(Contractor, contractor_id) is None:
        raise NotFound("Contractor not found")

    # Instant provisional suggestion; the escalation workflow refines it with the LLM.
    suggestion = classifier.classify_rules(data.title, data.description)
    severity = data.severity or suggestion.severity
    violation = Violation(
        mine_id=mine.id,
        inspection_id=data.inspection_id,
        contractor_id=contractor_id,
        kind=data.kind,
        category=data.category,
        title=data.title,
        description=data.description,
        severity=severity,
        severity_confirmed=data.severity is not None and principal.can(Perm.VIOLATION_CONFIRM),
        ai_suggested_severity=suggestion.severity,
        ai_confidence=suggestion.confidence,
        ai_rationale=suggestion.rationale,
        ai_source=suggestion.source,
        detected_by=detected_by,
        regulation_ref=data.regulation_ref or (", ".join(suggestion.regulation_refs) or None),
        latitude=data.geo.latitude if data.geo else None,
        longitude=data.geo.longitude if data.geo else None,
        occurred_at=data.occurred_at or datetime.now(UTC),
        reported_by=principal.id,
        confirmed_by=principal.id if data.severity and principal.can(Perm.VIOLATION_CONFIRM) else None,
        client_event_id=data.client_event_id,
    )
    session.add(violation)
    await session.flush()
    violation.workflow_id = escalation_workflow_id(violation.id)
    record_event(
        session, "violation.flagged", entity_type="violation", entity_id=violation.id, actor=principal,
        mine_id=mine.id, subsidiary_id=mine.subsidiary_id, after=snapshot(violation, V_FIELDS),
        data={"severity": severity.value, "kind": data.kind.value, "category": data.category.value,
              "contractor_id": str(contractor_id) if contractor_id else None},
    )
    if commit:
        await session.commit()
    return violation, True


async def reclassify(session: AsyncSession, principal: Principal, violation_id: uuid.UUID) -> Violation:
    """Run the LLM classifier synchronously (on demand from the UI)."""
    violation = await get_violation(session, principal, violation_id)
    scope = await visible_mine_ids(session, principal)
    suggestion = await classifier.classify(
        violation.title, violation.description, violation.category.value,
        visible_mine_ids=[str(m) for m in scope] if scope is not None else None,
    )
    apply_suggestion(violation, suggestion)
    await session.commit()
    return violation


def apply_suggestion(violation: Violation, suggestion: classifier.SeveritySuggestion) -> None:
    violation.ai_suggested_severity = suggestion.severity
    violation.ai_confidence = suggestion.confidence
    violation.ai_rationale = suggestion.rationale
    violation.ai_source = suggestion.source
    if not violation.severity_confirmed:
        violation.severity = suggestion.severity
    if suggestion.regulation_refs and not violation.regulation_ref:
        violation.regulation_ref = ", ".join(suggestion.regulation_refs)[:200]


async def confirm_severity(
    session: AsyncSession, principal: Principal, violation_id: uuid.UUID, data: ViolationConfirm
) -> Violation:
    principal.require(Perm.VIOLATION_CONFIRM)
    violation = await get_violation(session, principal, violation_id)
    await assert_mine_access(session, principal, violation.mine_id, write=True)
    before = snapshot(violation, V_FIELDS)
    violation.severity = data.severity
    violation.severity_confirmed = True
    violation.confirmed_by = principal.id
    record_event(
        session, "violation.severity_confirmed", entity_type="violation", entity_id=violation.id,
        actor=principal, mine_id=violation.mine_id, subsidiary_id=violation.mine.subsidiary_id,
        before=before, after=snapshot(violation, V_FIELDS),
        data={"agreed_with_ai": violation.ai_suggested_severity == data.severity, "notes": data.notes},
    )
    await session.commit()
    await temporal.signal(escalation_workflow_id(violation.id), "severity_changed", data.severity.value)
    return violation


async def close_violation(session: AsyncSession, principal: Principal, violation_id: uuid.UUID, notes: str) -> Violation:
    principal.require(Perm.ACTION_VERIFY)
    violation = await get_violation(session, principal, violation_id)
    await assert_mine_access(session, principal, violation.mine_id, write=True)
    if violation.status == ViolationStatus.CLOSED:
        raise InvalidState("Violation already closed")
    verified, pending = (
        await session.execute(
            select(
                func.count().filter(CorrectiveAction.status == ActionStatus.VERIFIED),
                func.count().filter(CorrectiveAction.status != ActionStatus.VERIFIED),
            ).where(CorrectiveAction.violation_id == violation.id)
        )
    ).one()
    if violation.severity in (Severity.HIGH, Severity.CRITICAL) and (pending or not verified):
        raise InvalidState("High/critical violations can only be closed after corrective actions are verified")
    before = snapshot(violation, V_FIELDS)
    violation.status = ViolationStatus.CLOSED
    violation.closed_at = datetime.now(UTC)
    record_event(
        session, "violation.closed", entity_type="violation", entity_id=violation.id, actor=principal,
        mine_id=violation.mine_id, subsidiary_id=violation.mine.subsidiary_id, before=before,
        after=snapshot(violation, V_FIELDS), data={"notes": notes, "manual": True},
    )
    await session.commit()
    await temporal.signal(escalation_workflow_id(violation.id), "closed")
    return violation


# --------------------------------------------------------- corrective actions
def _action_query(principal: Principal) -> Select[Any]:
    stmt = scope_mines(
        select(CorrectiveAction).join(Violation, CorrectiveAction.violation_id == Violation.id),
        principal,
        Violation.mine_id,
    )
    if principal.role == Role.CONTRACTOR:
        stmt = stmt.where(CorrectiveAction.assigned_to == principal.id)
    return stmt


async def list_actions(
    session: AsyncSession,
    principal: Principal,
    *,
    violation_id: uuid.UUID | None,
    status: ActionStatus | None,
    assigned_to_me: bool,
    offset: int,
    limit: int,
) -> tuple[list[CorrectiveAction], int]:
    stmt = _action_query(principal)
    if violation_id:
        stmt = stmt.where(CorrectiveAction.violation_id == violation_id)
    if status:
        stmt = stmt.where(CorrectiveAction.status == status)
    if assigned_to_me:
        stmt = stmt.where(CorrectiveAction.assigned_to == principal.id)
    total = (await session.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    rows = (
        await session.execute(stmt.order_by(CorrectiveAction.deadline).offset(offset).limit(limit))
    ).scalars().unique().all()
    return list(rows), int(total)


async def get_action(session: AsyncSession, principal: Principal, action_id: uuid.UUID) -> CorrectiveAction:
    row = (await session.execute(_action_query(principal).where(CorrectiveAction.id == action_id))).scalars().first()
    if row is None:
        raise NotFound("Corrective action not found")
    return row


async def assign_action(session: AsyncSession, principal: Principal, data: ActionCreate) -> CorrectiveAction:
    principal.require(Perm.ACTION_ASSIGN)
    violation = await get_violation(session, principal, data.violation_id)
    await assert_mine_access(session, principal, violation.mine_id, write=True)
    if violation.status == ViolationStatus.CLOSED:
        raise InvalidState("Cannot assign actions to a closed violation")
    if data.deadline <= datetime.now(UTC):
        raise InvalidState("Deadline must be in the future")
    assignee = await session.get(User, data.assigned_to)
    if assignee is None or assignee.status != UserStatus.ACTIVE:
        raise NotFound("Assignee not found or inactive")
    if assignee.role == Role.REGULATOR:
        raise InvalidState("Regulators cannot be assigned corrective actions")
    action = CorrectiveAction(
        violation_id=violation.id,
        title=data.title,
        description=data.description,
        assigned_to=assignee.id,
        assigned_by=principal.id,
        deadline=data.deadline,
    )
    session.add(action)
    before = snapshot(violation, V_FIELDS)
    if violation.status in (ViolationStatus.OPEN, ViolationStatus.ESCALATED, ViolationStatus.PENDING_VERIFICATION):
        violation.status = ViolationStatus.ACTION_ASSIGNED
    await session.flush()
    record_event(
        session, "action.assigned", entity_type="corrective_action", entity_id=action.id, actor=principal,
        mine_id=violation.mine_id, subsidiary_id=violation.mine.subsidiary_id,
        after=snapshot(action, A_FIELDS),
        data={"violation_id": str(violation.id), "assignee_id": str(assignee.id), "deadline": data.deadline.isoformat(),
              "violation_before": before},
    )
    await session.commit()
    await temporal.signal(
        escalation_workflow_id(violation.id), "action_assigned",
        {"action_id": str(action.id), "deadline": data.deadline.isoformat()},
    )
    return await get_action(session, principal, action.id)


def _ensure_assignee(principal: Principal, action: CorrectiveAction) -> None:
    if action.assigned_to != principal.id and principal.role not in (Role.ADMIN, Role.MINE_OFFICIAL):
        raise Forbidden("Only the assignee can update this action")


async def start_action(session: AsyncSession, principal: Principal, action_id: uuid.UUID) -> CorrectiveAction:
    principal.require(Perm.ACTION_EXECUTE)
    action = await get_action(session, principal, action_id)
    _ensure_assignee(principal, action)
    if action.status not in (ActionStatus.ASSIGNED, ActionStatus.REJECTED, ActionStatus.OVERDUE):
        raise InvalidState(f"Cannot start an action in status {action.status.value}")
    before = snapshot(action, A_FIELDS)
    action.status = ActionStatus.IN_PROGRESS
    record_event(
        session, "action.started", entity_type="corrective_action", entity_id=action.id, actor=principal,
        mine_id=action.violation.mine_id, before=before, after=snapshot(action, A_FIELDS),
        data={"violation_id": str(action.violation_id)},
    )
    await session.commit()
    return action


async def submit_action(
    session: AsyncSession, principal: Principal, action_id: uuid.UUID, data: ActionSubmit
) -> CorrectiveAction:
    principal.require(Perm.ACTION_EXECUTE)
    action = await get_action(session, principal, action_id)
    _ensure_assignee(principal, action)
    if action.status not in (ActionStatus.ASSIGNED, ActionStatus.IN_PROGRESS, ActionStatus.REJECTED, ActionStatus.OVERDUE):
        raise InvalidState(f"Cannot submit an action in status {action.status.value}")
    before = snapshot(action, A_FIELDS)
    action.status = ActionStatus.SUBMITTED
    action.completion_notes = data.completion_notes
    action.submitted_at = datetime.now(UTC)
    violation = action.violation
    violation.status = ViolationStatus.PENDING_VERIFICATION
    record_event(
        session, "action.submitted", entity_type="corrective_action", entity_id=action.id, actor=principal,
        mine_id=violation.mine_id, before=before, after=snapshot(action, A_FIELDS),
        data={"violation_id": str(violation.id)},
    )
    await session.commit()
    await temporal.signal(escalation_workflow_id(violation.id), "action_submitted", str(action.id))
    return action


async def verify_action(
    session: AsyncSession, principal: Principal, action_id: uuid.UUID, data: ActionVerify
) -> CorrectiveAction:
    principal.require(Perm.ACTION_VERIFY)
    action = await get_action(session, principal, action_id)
    violation = action.violation
    await assert_mine_access(session, principal, violation.mine_id, write=True)
    if action.status != ActionStatus.SUBMITTED:
        raise InvalidState("Only submitted actions can be verified")
    if action.assigned_to == principal.id:
        raise Forbidden("Segregation of duties: you cannot verify your own corrective action")
    if data.reinspection_id:
        reinspection = await session.get(Inspection, data.reinspection_id)
        if reinspection is None or reinspection.mine_id != violation.mine_id:
            raise InvalidState("Re-inspection must belong to the same mine")
    before = snapshot(action, A_FIELDS)
    v_before = snapshot(violation, V_FIELDS)
    now = datetime.now(UTC)
    action.verified_by = principal.id
    action.verified_at = now
    action.verification_notes = data.notes
    action.reinspection_id = data.reinspection_id
    approved = data.decision == "approve"
    if approved:
        action.status = ActionStatus.VERIFIED
        remaining = (
            await session.execute(
                select(func.count()).where(
                    CorrectiveAction.violation_id == violation.id,
                    CorrectiveAction.id != action.id,
                    CorrectiveAction.status != ActionStatus.VERIFIED,
                )
            )
        ).scalar_one()
        if remaining == 0:
            violation.status = ViolationStatus.CLOSED
            violation.closed_at = now
        else:
            violation.status = ViolationStatus.ACTION_ASSIGNED
    else:
        action.status = ActionStatus.REJECTED
        violation.status = ViolationStatus.ACTION_ASSIGNED
    record_event(
        session, "action.verified" if approved else "action.rejected", entity_type="corrective_action",
        entity_id=action.id, actor=principal, mine_id=violation.mine_id,
        subsidiary_id=violation.mine.subsidiary_id, before=before, after=snapshot(action, A_FIELDS),
        data={"violation_id": str(violation.id), "violation_closed": violation.status == ViolationStatus.CLOSED,
              "assignee_id": str(action.assigned_to)},
    )
    if violation.status == ViolationStatus.CLOSED:
        record_event(
            session, "violation.closed", entity_type="violation", entity_id=violation.id, actor=principal,
            mine_id=violation.mine_id, subsidiary_id=violation.mine.subsidiary_id, before=v_before,
            after=snapshot(violation, V_FIELDS), data={"via_action": str(action.id)},
        )
    await session.commit()
    await temporal.signal(
        escalation_workflow_id(violation.id), "action_verified", {"action_id": str(action.id), "approved": approved}
    )
    return action
