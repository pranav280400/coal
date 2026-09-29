"""Kafka consumer handlers — independent consumer groups fanning out the same streams.

* audit         — hash-chained, write-once audit trail (FR15)
* notifications — in-app / email / SMS / push alerts & escalations
* analytics     — dashboard cache invalidation (cached aggregates, NFR latency)
* orchestrator  — starts/signals Temporal workflows from domain events
* ingest        — materialises mobile field events into Postgres (FR4)
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from temporalio.common import WorkflowIDConflictPolicy, WorkflowIDReusePolicy

from app.consumers.base import claim
from app.core.metrics import AUDIT_CHAIN_LENGTH
from app.core.redis import cache_delete_pattern
from app.models import User
from app.models.enums import NotificationSeverity, Role, UserStatus
from app.schemas.field import IngestEvent
from app.services import audit as audit_svc
from app.services import ingest as ingest_svc
from app.services import notifications as notify_svc
from app.services.dashboard import DASH_PREFIX
from app.workflows import client as temporal

logger = logging.getLogger(__name__)


def _u(value: Any) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(value)) if value else None
    except ValueError:
        return None


# =================================================================== audit
async def handle_audit(session: AsyncSession, event: dict[str, Any]) -> None:
    entry = await audit_svc.append(session, event)
    if entry is not None:
        AUDIT_CHAIN_LENGTH.set(entry.id)


# ========================================================= notifications
_SEV = NotificationSeverity


async def _users(session: AsyncSession, *ids: Any) -> list[User]:
    wanted = [u for u in (_u(i) for i in ids) if u]
    if not wanted:
        return []
    rows = (await session.execute(select(User).where(User.id.in_(wanted), User.status == UserStatus.ACTIVE))).scalars()
    return list(rows.unique().all())


async def _admins(session: AsyncSession) -> list[User]:
    return list(
        (await session.execute(select(User).where(User.role == Role.ADMIN, User.status == UserStatus.ACTIVE)))
        .scalars().unique().all()
    )


async def handle_notifications(session: AsyncSession, event: dict[str, Any]) -> None:
    etype: str = event["event_type"]
    data: dict[str, Any] = event.get("data") or {}
    after: dict[str, Any] = event.get("after") or {}
    mine_id = _u(event.get("mine_id"))
    eid = event["event_id"]
    entity_id = event["entity_id"]
    actor_id = (event.get("actor") or {}).get("id")
    if data.get("seeded"):
        return  # baseline imports must not trigger e-mail/SMS storms

    async def send(users: list[User], title: str, body: str, sev: NotificationSeverity, category: str,
                   link: str | None, *, sms: bool = False) -> None:
        users = [u for u in users if str(u.id) != actor_id]  # don't notify people about their own actions
        if users:
            await notify_svc.notify(session, users, title=title, body=body, severity=sev, category=category,
                                    link=link, source_event_id=eid, sms=sms)

    if etype == "violation.flagged":
        sev = data.get("severity", "medium")
        title = after.get("title") or "New violation"
        roles = [Role.MINE_OFFICIAL] + ([Role.CORPORATE] if sev in ("high", "critical") else [])
        users = await notify_svc.recipients_for_mine(session, mine_id, roles, include_hq=sev == "critical")
        label = {"ai": "AI-detected", "system": "Limit exceeded —"}.get(str(data.get("detected_by")), "Reported")
        await send(users, f"{label} {sev} violation: {title}",
                   f"VIO-{after.get('number')} ({data.get('category')}) requires attention. "
                   "Assign a corrective action within the SLA to avoid escalation.",
                   _SEV.CRITICAL if sev == "critical" else _SEV.WARNING if sev == "high" else _SEV.INFO,
                   "violation", f"/violations/{entity_id}", sms=sev == "critical")
    elif etype == "violation.escalated":
        level = int(data.get("level", 1))
        roles = [Role.MINE_OFFICIAL] if level <= 1 else [Role.MINE_OFFICIAL, Role.CORPORATE]
        users = await notify_svc.recipients_for_mine(session, mine_id, roles, include_hq=level >= 3)
        if level >= 3 and data.get("severity") == "critical":
            users += list((await session.execute(
                select(User).where(User.role == Role.REGULATOR, User.status == UserStatus.ACTIVE)
            )).scalars().unique().all())
        await send(users, f"Escalation L{level}: VIO-{data.get('number')} {data.get('title', '')}",
                   str(data.get("reason", "Violation escalated")), _SEV.CRITICAL if level >= 2 else _SEV.WARNING,
                   "escalation", f"/violations/{entity_id}", sms=level >= 2)
    elif etype == "action.assigned":
        await send(await _users(session, data.get("assignee_id")), "Corrective action assigned to you",
                   f"{after.get('title')} — due {str(data.get('deadline', ''))[:16].replace('T', ' ')} UTC.",
                   _SEV.WARNING, "action", f"/corrective-actions/{entity_id}")
    elif etype == "action.submitted":
        users = await notify_svc.recipients_for_mine(session, mine_id, [Role.MINE_OFFICIAL])
        await send(users, "Corrective action awaiting verification",
                   f"{after.get('title')} was submitted and needs verification.", _SEV.INFO, "action",
                   f"/corrective-actions/{entity_id}")
    elif etype in ("action.verified", "action.rejected"):
        ok = etype == "action.verified"
        await send(await _users(session, data.get("assignee_id")),
                   "Corrective action verified" if ok else "Corrective action rejected",
                   (after.get("verification_notes") or "") + (" The violation is now closed." if data.get("violation_closed") else ""),
                   _SEV.INFO if ok else _SEV.WARNING, "action", f"/corrective-actions/{entity_id}")
    elif etype == "action.overdue":
        users = await _users(session, data.get("assignee_id"))
        users += await notify_svc.recipients_for_mine(session, mine_id, [Role.MINE_OFFICIAL])
        await send(users, f"Overdue corrective action: {data.get('title')}",
                   f"The deadline {str(data.get('deadline', ''))[:10]} has passed.", _SEV.WARNING, "action",
                   f"/corrective-actions/{entity_id}")
    elif etype == "action.verification_pending":
        users = await notify_svc.recipients_for_mine(session, mine_id, [Role.MINE_OFFICIAL, Role.CORPORATE])
        await send(users, f"Verification pending for VIO-{data.get('number')}",
                   "Submitted corrective actions have awaited verification for over 72 hours.", _SEV.WARNING,
                   "action", f"/violations/{entity_id}")
    elif etype == "compliance.reminder":
        users = await _users(session, data.get("owner_id")) or await notify_svc.recipients_for_mine(
            session, mine_id, [Role.MINE_OFFICIAL])
        days = int(data.get("days_left", 0))
        await send(users, f"Due in {days} day{'s' if days != 1 else ''}: {data.get('title')}",
                   f"{data.get('mine_name')} — statutory obligation due on {data.get('due_date')}.",
                   _SEV.WARNING if days <= 1 else _SEV.INFO, "compliance", f"/compliance?item={entity_id}")
    elif etype == "compliance.escalated":
        users = await _users(session, data.get("owner_id"))
        users += await notify_svc.recipients_for_mine(session, mine_id, [Role.MINE_OFFICIAL, Role.CORPORATE])
        await send(users, f"Overdue statutory compliance: {data.get('title')}",
                   f"{data.get('mine_name')} — {data.get('days_overdue')} day(s) overdue. Escalated to corporate.",
                   _SEV.CRITICAL, "compliance", f"/compliance?item={entity_id}")
    elif etype == "inspection.geofence_mismatch":
        users = await notify_svc.recipients_for_mine(session, mine_id, [Role.MINE_OFFICIAL, Role.CORPORATE])
        await send(users, "Inspection geo-tag outside mine boundary",
                   f"Reported location is {data.get('distance_km')} km from the mine (limit {data.get('radius_km')} km). "
                   "Please verify the field report.", _SEV.WARNING, "inspection", f"/inspections/{entity_id}")
    elif etype == "anomaly.detected":
        users = await notify_svc.recipients_for_mine(session, mine_id, [Role.MINE_OFFICIAL, Role.CORPORATE])
        await send(users, str(data.get("title", "Anomaly detected")), str(data.get("description", "")),
                   _SEV.WARNING, "anomaly", "/reports?tab=anomalies")
    elif etype == "risk.high_detected":
        users = await notify_svc.recipients_for_mine(session, mine_id, [Role.MINE_OFFICIAL, Role.CORPORATE],
                                                     include_hq=True)
        drivers = ", ".join(d["label"] for d in data.get("drivers", [])[:3])
        await send(users, f"High compliance risk: {data.get('mine_name')} ({data.get('score')})",
                   f"Main drivers: {drivers}. Prioritise inspection and corrective actions.", _SEV.CRITICAL,
                   "risk", "/reports?tab=risk")
    elif etype in ("document.processed", "document.failed"):
        ok = etype == "document.processed"
        await send(await _users(session, data.get("uploaded_by")),
                   f"Document {'digitised' if ok else 'processing failed'}: {data.get('title')}",
                   (f"{data.get('chunks') or 0} searchable sections indexed." if ok else str(data.get("error"))),
                   _SEV.INFO if ok else _SEV.WARNING, "document", f"/documents/{entity_id}")
    elif etype == "report.ready":
        users = await _users(session, data.get("requested_by"))
        if data.get("scheduled"):
            users += list((await session.execute(select(User).where(
                User.role.in_([Role.CORPORATE, Role.REGULATOR]), User.status == UserStatus.ACTIVE
            ))).scalars().unique().all())
        await send(users, "Compliance report ready", str(data.get("title")), _SEV.INFO, "report",
                   f"/reports?report={entity_id}")
    elif etype.startswith("grievance."):
        await _grievance_notifications(session, etype, event, data, send)
    elif etype == "user.access_requested":
        await send(await _admins(session), "New access request",
                   f"{after.get('email')} requested {after.get('role')} access.", _SEV.INFO, "user", "/users?status=pending")
    elif etype == "user.approved":
        users = await _users(session, entity_id)
        await send(users, "Your Lumen access is approved", "You can now sign in.", _SEV.INFO, "user", "/dashboard")
    elif etype == "contractor.registered":
        users = list((await session.execute(select(User).where(
            User.role == Role.CORPORATE, User.status == UserStatus.ACTIVE,
            (User.subsidiary_id == _u(event.get("subsidiary_id"))) | User.subsidiary_id.is_(None),
        ))).scalars().unique().all())
        await send(users, "Contractor pending verification", f"{after.get('name')} ({after.get('registration_no')})",
                   _SEV.INFO, "contractor", f"/contractors/{entity_id}")


async def _grievance_notifications(session: AsyncSession, etype: str, event: dict[str, Any],
                                   data: dict[str, Any], send: Any) -> None:
    mine_id = _u(event.get("mine_id"))
    link = f"/grievances/{event['entity_id']}"
    ref = f"GRV-{data.get('number')}"
    subject = str(data.get("subject", ""))
    raiser = await _users(session, data.get("raiser_id"))
    if etype == "grievance.raised":
        prio = data.get("priority", "medium")
        roles = [Role.MINE_OFFICIAL] + ([Role.CORPORATE] if prio in ("high", "critical") else [])
        await send(await notify_svc.recipients_for_mine(session, mine_id, roles),
                   f"New grievance {ref}: {subject}",
                   f"{str(data.get('category', '')).replace('_', ' ').capitalize()} · {prio} priority at "
                   f"{data.get('mine_name')}. Assign an owner before the resolution deadline.",
                   _SEV.WARNING if prio in ("high", "critical") else _SEV.INFO, "grievance", link)
    elif etype == "grievance.assigned":
        await send(await _users(session, data.get("assignee_id")), f"Grievance {ref} assigned to you", subject,
                   _SEV.WARNING, "grievance", link)
        await send(raiser, f"Your grievance {ref} has an owner",
                   "It has been assigned for resolution. You will be notified when it is resolved.",
                   _SEV.INFO, "grievance", link)
    elif etype in ("grievance.resolved", "grievance.rejected"):
        ok = etype == "grievance.resolved"
        await send(raiser, f"Your grievance {ref} was {'resolved' if ok else 'not upheld'}",
                   ("Please confirm and rate the resolution, or reopen it if the issue remains."
                    if ok else "You can reopen it with more detail if you disagree."),
                   _SEV.INFO if ok else _SEV.WARNING, "grievance", link)
    elif etype == "grievance.reopened":
        users = await _users(session, data.get("assignee_id"))
        users += await notify_svc.recipients_for_mine(session, mine_id, [Role.MINE_OFFICIAL])
        await send(users, f"Grievance {ref} reopened", str(data.get("reason", subject)), _SEV.WARNING,
                   "grievance", link)
    elif etype == "grievance.escalated":
        level = int(data.get("level", 1))
        roles = [Role.MINE_OFFICIAL] if level <= 1 else [Role.MINE_OFFICIAL, Role.CORPORATE]
        users = await notify_svc.recipients_for_mine(session, mine_id, roles, include_hq=level >= 3)
        users += await _users(session, data.get("assignee_id"))
        await send(users, f"Escalation L{level}: grievance {ref} past its deadline",
                   f"{subject} — {data.get('mine_name')}. Resolve it or record why it cannot be upheld.",
                   _SEV.CRITICAL if level >= 2 else _SEV.WARNING, "escalation", link, sms=level >= 2)


# =============================================================== analytics
_DASHBOARD_EVENTS = ("violation.", "inspection.", "compliance.", "action.", "contractor.", "contract.",
                     "risk.", "anomaly.", "mine.", "attendance.", "grievance.", "production.",
                     "environment.")


async def handle_analytics(session: AsyncSession, event: dict[str, Any]) -> None:
    if event["event_type"].startswith(_DASHBOARD_EVENTS):
        # Scoped aggregates are cheap to rebuild; invalidating all scopes keeps rollups consistent.
        await cache_delete_pattern(f"{DASH_PREFIX}*")


# ============================================================ orchestrator
async def handle_orchestrator(session: AsyncSession, event: dict[str, Any]) -> None:
    etype: str = event["event_type"]
    eid = event["entity_id"]
    data = event.get("data") or {}
    if etype == "violation.flagged":
        await temporal.start_workflow("ViolationEscalationWorkflow", {"violation_id": eid},
                                      workflow_id=f"violation-escalation-{eid}")
    elif etype == "inspection.submitted":
        await temporal.start_workflow("FieldIngestAgentWorkflow", eid, workflow_id=f"field-ingest-{eid}")
    elif etype == "compliance.created":
        await temporal.start_workflow("ComplianceReminderWorkflow", {"item_id": eid},
                                      workflow_id=f"compliance-reminder-{eid}")
    elif etype in ("compliance.updated", "compliance.completed"):
        # Signal-with-start: wakes the running workflow (or starts one if it had finished).
        await temporal.start_workflow(
            "ComplianceReminderWorkflow", {"item_id": eid}, workflow_id=f"compliance-reminder-{eid}",
            start_signal="updated", id_conflict_policy=WorkflowIDConflictPolicy.USE_EXISTING,
            id_reuse_policy=WorkflowIDReusePolicy.ALLOW_DUPLICATE,
        )
    elif etype == "compliance.deleted":
        await temporal.signal(f"compliance-reminder-{eid}", "updated")
    elif etype == "document.uploaded":
        await temporal.start_workflow("DocumentDigitizationWorkflow", eid, workflow_id=f"document-digitize-{eid}")
    elif etype == "document.reprocess_requested":
        await temporal.start_workflow("DocumentDigitizationWorkflow", eid, workflow_id=data["workflow_id"])
    elif etype == "report.requested":
        await temporal.start_workflow("ReportGenerationWorkflow", eid, workflow_id=f"report-generation-{eid}")
    elif etype == "grievance.raised":
        await temporal.start_workflow("GrievanceSLAWorkflow", {"grievance_id": eid},
                                      workflow_id=f"grievance-sla-{eid}")
    elif etype.startswith("grievance.") and etype != "grievance.escalated":
        # Signal-with-start so a reopened grievance gets its SLA timer back.
        await temporal.start_workflow(
            "GrievanceSLAWorkflow", {"grievance_id": eid}, workflow_id=f"grievance-sla-{eid}",
            start_signal="updated", id_conflict_policy=WorkflowIDConflictPolicy.USE_EXISTING,
            id_reuse_policy=WorkflowIDReusePolicy.ALLOW_DUPLICATE,
        )
    elif etype == "regulation.created":
        await temporal.start_workflow("KnowledgeIndexWorkflow", False,
                                      workflow_id=f"knowledge-index-{eid}")


# ================================================================== ingest
async def handle_ingest(session: AsyncSession, envelope: dict[str, Any]) -> None:
    event = IngestEvent.model_validate({
        "client_event_id": envelope["client_event_id"],
        "event_type": envelope["event_type"],
        "captured_at": envelope["captured_at"],
        "payload": envelope["payload"],
    })
    try:
        status, etype, eid = await ingest_svc.process(session, uuid.UUID(envelope["user_id"]), event)
        await ingest_svc.set_status(event.client_event_id, status, entity_type=etype, entity_id=eid)
    except (ValueError, PermissionError) as exc:
        # Business rejection is final (not retried); the device shows the reason.
        await session.rollback()
        await ingest_svc.set_status(event.client_event_id, "rejected", detail=str(exc))
        await claim(session, "ingest", event.client_event_id)
