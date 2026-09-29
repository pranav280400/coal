"""Temporal activities: all side effects (DB, LLM, OCR, storage, events) live here.

Activities are idempotent where possible because Temporal retries them.
Notifications are not sent directly: activities record domain events via the
outbox and the notification consumer fans them out, keeping one delivery path.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import select
from temporalio import activity
from temporalio.exceptions import ApplicationError

from app.ai import classifier, ocr, rag, vectorstore
from app.ai.llm import LLMUnavailable
from app.core import storage
from app.core.config import get_settings
from app.core.db import session_scope
from app.core.metrics import ESCALATIONS
from app.models import (
    AuditLog,
    ComplianceItem,
    CorrectiveAction,
    Document,
    Inspection,
    MediaFile,
    Mine,
    Regulation,
    Report,
    Subsidiary,
    Violation,
)
from app.models.base import snapshot
from app.models.enums import (
    ActionStatus,
    ComplianceCategory,
    ComplianceStatus,
    DetectedBy,
    DocumentType,
    InspectionOutcome,
    InspectionStatus,
    ProcessingStatus,
    ReportScope,
    Severity,
    ViolationStatus,
)
from app.services import analytics as analytics_svc
from app.services import compliance as compliance_svc
from app.services import reports as report_svc
from app.services.events import record_event
from app.services.violations import V_FIELDS, apply_suggestion

logger = logging.getLogger(__name__)


def _uuid(value: str) -> uuid.UUID:
    return uuid.UUID(str(value))


# ================================================================ violations
@dataclass
class ViolationState:
    exists: bool
    status: str = "open"
    severity: str = "medium"
    escalation_level: int = 0
    mine_id: str | None = None
    # [{id, status, deadline(iso)}] for actions that are not yet verified
    open_actions: list[dict[str, Any]] | None = None
    has_actions: bool = False


@activity.defn
async def load_violation_state(violation_id: str) -> dict[str, Any]:
    async with session_scope() as session:
        v = await session.get(Violation, _uuid(violation_id))
        if v is None:
            return asdict(ViolationState(exists=False))
        actions = (
            await session.execute(select(CorrectiveAction).where(CorrectiveAction.violation_id == v.id))
        ).scalars().unique().all()
        return asdict(
            ViolationState(
                exists=True,
                status=v.status.value,
                severity=v.severity.value,
                escalation_level=v.escalation_level,
                mine_id=str(v.mine_id),
                open_actions=[
                    {"id": str(a.id), "status": a.status.value, "deadline": a.deadline.isoformat()}
                    for a in actions
                    if a.status != ActionStatus.VERIFIED
                ],
                has_actions=bool(actions),
            )
        )


@activity.defn
async def classify_violation_ai(violation_id: str) -> str:
    """Refine the provisional rule-based severity with the LLM (grounded via Qdrant)."""
    async with session_scope() as session:
        v = await session.get(Violation, _uuid(violation_id))
        if v is None:
            return "missing"
        mine = await session.get(Mine, v.mine_id)
        title, description, category = v.title, v.description, v.category.value
    suggestion = await classifier.classify(
        title, description, category, visible_mine_ids=[str(mine.id)] if mine else None
    )
    async with session_scope() as session:
        v = await session.get(Violation, _uuid(violation_id))
        if v is None:
            return "missing"
        before = snapshot(v, V_FIELDS)
        apply_suggestion(v, suggestion)
        if suggestion.source == "llm":
            record_event(
                session, "violation.ai_classified", entity_type="violation", entity_id=v.id, actor=None,
                mine_id=v.mine_id, before=before, after=snapshot(v, V_FIELDS),
                data={"suggested": suggestion.severity.value, "confidence": suggestion.confidence},
            )
    return suggestion.severity.value


@activity.defn
async def index_violation(violation_id: str) -> int:
    async with session_scope() as session:
        v = await session.get(Violation, _uuid(violation_id))
        if v is None:
            return 0
        mine = await session.get(Mine, v.mine_id)
        text = (
            f"Violation VIO-{v.number} at {mine.name if mine else ''} ({v.category.value}, severity {v.severity.value}, "
            f"status {v.status.value}). {v.description}\nRegulation: {v.regulation_ref or 'n/a'}"
        )
        return await vectorstore.upsert_source(
            source_type="violation", source_id=str(v.id), title=v.title, text=text,
            mine_id=str(v.mine_id), subsidiary_id=str(mine.subsidiary_id) if mine else None,
            category=v.category.value,
        )


def _escalation_target(level: int) -> str:
    return {1: "mine_management", 2: "subsidiary_corporate"}.get(level, "headquarters")


@activity.defn
async def escalate_violation(violation_id: str, level: int, reason: str) -> int:
    s = get_settings()
    level = min(level, s.max_escalation_level)
    async with session_scope() as session:
        v = await session.get(Violation, _uuid(violation_id))
        if v is None or v.status == ViolationStatus.CLOSED:
            return 0
        before = snapshot(v, V_FIELDS)
        v.escalation_level = max(v.escalation_level, level)
        if v.status == ViolationStatus.OPEN:
            v.status = ViolationStatus.ESCALATED
        record_event(
            session, "violation.escalated", entity_type="violation", entity_id=v.id, actor=None,
            mine_id=v.mine_id, subsidiary_id=v.mine.subsidiary_id, before=before, after=snapshot(v, V_FIELDS),
            data={"level": level, "target": _escalation_target(level), "reason": reason,
                  "severity": v.severity.value, "title": v.title, "number": v.number},
        )
    ESCALATIONS.labels("violation", str(level)).inc()
    return level


@activity.defn
async def mark_actions_overdue(violation_id: str) -> list[str]:
    now = datetime.now(UTC)
    marked: list[str] = []
    async with session_scope() as session:
        actions = (
            await session.execute(
                select(CorrectiveAction).where(
                    CorrectiveAction.violation_id == _uuid(violation_id),
                    CorrectiveAction.deadline < now,
                    CorrectiveAction.status.in_([ActionStatus.ASSIGNED, ActionStatus.IN_PROGRESS, ActionStatus.REJECTED]),
                )
            )
        ).scalars().unique().all()
        for a in actions:
            a.status = ActionStatus.OVERDUE
            record_event(
                session, "action.overdue", entity_type="corrective_action", entity_id=a.id, actor=None,
                mine_id=a.violation.mine_id,
                data={"violation_id": violation_id, "assignee_id": str(a.assigned_to), "title": a.title,
                      "deadline": a.deadline.isoformat()},
            )
            marked.append(str(a.id))
    return marked


@activity.defn
async def remind_verification_pending(violation_id: str) -> None:
    async with session_scope() as session:
        v = await session.get(Violation, _uuid(violation_id))
        if v is None or v.status != ViolationStatus.PENDING_VERIFICATION:
            return
        record_event(
            session, "action.verification_pending", entity_type="violation", entity_id=v.id, actor=None,
            mine_id=v.mine_id, data={"title": v.title, "number": v.number},
        )


@activity.defn
async def refresh_mine_risk(mine_id: str) -> float | None:
    async with session_scope() as session:
        score = await analytics_svc.recompute_mine_risk(session, _uuid(mine_id))
        await analytics_svc.detect_recurring_for_mine(session, _uuid(mine_id))
    return score


# ================================================================ compliance
@activity.defn
async def load_compliance_state(item_id: str) -> dict[str, Any]:
    async with session_scope() as session:
        item = await session.get(ComplianceItem, _uuid(item_id))
        if item is None:
            return {"exists": False}
        return {
            "exists": True,
            "status": item.status.value,
            "due_date": item.due_date.isoformat(),
            "frequency": item.frequency.value,
            "escalated": item.escalated,
        }


@activity.defn
async def send_compliance_reminder(item_id: str, days_left: int) -> None:
    async with session_scope() as session:
        item = await session.get(ComplianceItem, _uuid(item_id))
        if item is None or item.status in (ComplianceStatus.COMPLIANT,):
            return
        record_event(
            session, "compliance.reminder", entity_type="compliance_item", entity_id=item.id, actor=None,
            mine_id=item.mine_id, subsidiary_id=item.mine.subsidiary_id,
            data={"days_left": days_left, "title": item.title, "due_date": item.due_date.isoformat(),
                  "owner_id": str(item.owner_id) if item.owner_id else None, "mine_name": item.mine.name},
        )


@activity.defn
async def escalate_overdue_compliance(item_id: str, repeat: int) -> bool:
    async with session_scope() as session:
        item = await session.get(ComplianceItem, _uuid(item_id))
        if item is None or item.status == ComplianceStatus.COMPLIANT:
            return False
        today = datetime.now(UTC).date()
        if item.due_date >= today:
            return False
        before = snapshot(item, compliance_svc.AUDIT_FIELDS)
        if item.status in (ComplianceStatus.DUE, ComplianceStatus.IN_PROGRESS):
            item.status = ComplianceStatus.OVERDUE
        item.escalated = True
        record_event(
            session, "compliance.escalated", entity_type="compliance_item", entity_id=item.id, actor=None,
            mine_id=item.mine_id, subsidiary_id=item.mine.subsidiary_id, before=before,
            after=snapshot(item, compliance_svc.AUDIT_FIELDS),
            data={"title": item.title, "days_overdue": (today - item.due_date).days, "repeat": repeat,
                  "mine_name": item.mine.name, "owner_id": str(item.owner_id) if item.owner_id else None},
        )
    ESCALATIONS.labels("compliance", str(min(repeat + 1, 3))).inc()
    return True


@activity.defn
async def compliance_sweep() -> dict[str, Any]:
    """Daily: flip past-due items to overdue and return open item ids needing a reminder workflow."""
    async with session_scope() as session:
        changed = await compliance_svc.refresh_statuses(session)
        open_ids = (
            await session.execute(
                select(ComplianceItem.id).where(ComplianceItem.status != ComplianceStatus.COMPLIANT)
            )
        ).scalars().all()
    return {"newly_overdue": len(changed), "open_item_ids": [str(i) for i in open_ids]}


# ============================================================ field ingest AI
@activity.defn
async def ocr_inspection_attachments(inspection_id: str) -> int:
    async with session_scope() as session:
        media = (
            await session.execute(
                select(MediaFile).where(MediaFile.entity_type == "inspection",
                                        MediaFile.entity_id == _uuid(inspection_id),
                                        MediaFile.ocr_text.is_(None))
            )
        ).scalars().all()
        items = [(m.id, m.storage_key, m.content_type) for m in media]
    processed = 0
    for media_id, key, ctype in items:
        if not ocr.tesseract_available() and ctype != "application/pdf":
            continue
        try:
            result = await ocr.extract_text(await storage.get_object(key), ctype)
        except (ocr.OCRUnavailable, ValueError) as exc:
            logger.info("skip OCR for media %s: %s", media_id, exc)
            continue
        async with session_scope() as session:
            m = await session.get(MediaFile, media_id)
            if m:
                m.ocr_text = result.text[:100_000]
        processed += 1
    return processed


@activity.defn
async def summarize_inspection_ai(inspection_id: str) -> dict[str, Any]:
    async with session_scope() as session:
        insp = await session.get(Inspection, _uuid(inspection_id))
        if insp is None:
            return {}
        insp.status = InspectionStatus.PROCESSING
        media = (
            await session.execute(select(MediaFile).where(MediaFile.entity_type == "inspection",
                                                          MediaFile.entity_id == insp.id))
        ).scalars().all()
        payload = {
            "mine": insp.mine.name, "type": insp.inspection_type.value, "title": insp.title,
            "date": insp.inspected_at.isoformat(), "notes": insp.notes, "checklist": insp.checklist,
            "geo_verified": insp.geo_verified, "photo_evidence_count": len(media),
            "ocr_text_from_attachments": [m.ocr_text[:1500] for m in media if m.ocr_text],
        }
    try:
        result = await rag.summarize_inspection(payload)
    except LLMUnavailable as exc:
        raise ApplicationError("LLM unavailable", non_retryable=False) from exc
    async with session_scope() as session:
        insp = await session.get(Inspection, _uuid(inspection_id))
        if insp:
            insp.ai_summary = str(result.get("summary", ""))[:5000]
            insp.ai_findings = result
    return result


@activity.defn
async def create_ai_violations(inspection_id: str, hazards: list[dict[str, Any]]) -> list[str]:
    """Turn LLM-identified hazards into AI-detected violations awaiting human confirmation."""
    created: list[str] = []
    valid_sev = {s.value for s in Severity}
    valid_cat = {"safety", "environment", "production", "labour"}
    async with session_scope() as session:
        insp = await session.get(Inspection, _uuid(inspection_id))
        if insp is None or insp.outcome == InspectionOutcome.COMPLIANT:
            return created
        existing = (
            await session.execute(select(Violation.title).where(Violation.inspection_id == insp.id))
        ).scalars().all()
        existing_lower = {t.lower() for t in existing}
        for hz in hazards[:10]:
            desc = str(hz.get("description", "")).strip()
            sev = str(hz.get("severity", "medium")).lower()
            cat = str(hz.get("category", "safety")).lower()
            if len(desc) < 8 or sev not in valid_sev or sev == "low":
                continue
            title = desc[:120]
            if title.lower() in existing_lower:
                continue
            v = Violation(
                mine_id=insp.mine_id, inspection_id=insp.id,
                category=ComplianceCategory(cat if cat in valid_cat else "safety"),
                title=title, description=f"AI-identified from inspection INS-{insp.number}: {desc}",
                severity=Severity(sev), severity_confirmed=False, ai_suggested_severity=Severity(sev),
                ai_confidence=0.6, ai_rationale="Extracted by the inspection analysis agent; requires confirmation.",
                ai_source="llm", detected_by=DetectedBy.AI, occurred_at=insp.inspected_at,
                reported_by=insp.inspector_id, latitude=insp.latitude, longitude=insp.longitude,
            )
            session.add(v)
            await session.flush()
            v.workflow_id = f"violation-escalation-{v.id}"
            record_event(
                session, "violation.flagged", entity_type="violation", entity_id=v.id, actor=None,
                mine_id=insp.mine_id, subsidiary_id=insp.mine.subsidiary_id, after=snapshot(v, V_FIELDS),
                data={"severity": sev, "kind": "violation", "category": v.category.value,
                      "detected_by": "ai", "inspection_id": str(insp.id)},
            )
            created.append(str(v.id))
    return created


@activity.defn
async def index_inspection(inspection_id: str) -> int:
    async with session_scope() as session:
        insp = await session.get(Inspection, _uuid(inspection_id))
        if insp is None:
            return 0
        failed = [c for c in (insp.checklist or []) if not c.get("passed")]
        text = (
            f"Inspection INS-{insp.number} ({insp.inspection_type.value}) at {insp.mine.name} on "
            f"{insp.inspected_at:%d %b %Y}. Outcome: {insp.outcome.value}.\n{insp.notes}\n"
            + ("Failed checks: " + "; ".join(f"{c.get('item')}: {c.get('note') or ''}" for c in failed) + "\n" if failed else "")
            + (f"AI summary: {insp.ai_summary}" if insp.ai_summary else "")
        )
        count = await vectorstore.upsert_source(
            source_type="inspection", source_id=str(insp.id), title=insp.title, text=text,
            mine_id=str(insp.mine_id), subsidiary_id=str(insp.mine.subsidiary_id),
        )
        if insp.status == InspectionStatus.PROCESSING:
            insp.status = InspectionStatus.SUBMITTED
        return count


@activity.defn
async def finish_inspection_processing(inspection_id: str) -> str | None:
    async with session_scope() as session:
        insp = await session.get(Inspection, _uuid(inspection_id))
        if insp is None:
            return None
        if insp.status == InspectionStatus.PROCESSING:
            insp.status = InspectionStatus.SUBMITTED
        record_event(session, "inspection.processed", entity_type="inspection", entity_id=insp.id, actor=None,
                     mine_id=insp.mine_id, data={"has_ai_summary": bool(insp.ai_summary)})
        return str(insp.mine_id)


# ============================================================== documents
@activity.defn
async def digitize_document(document_id: str) -> dict[str, Any]:
    async with session_scope() as session:
        doc = await session.get(Document, _uuid(document_id))
        if doc is None:
            return {"missing": True}
        doc.ocr_status = ProcessingStatus.PROCESSING
        key, ctype, lang = doc.storage_key, doc.content_type, doc.language
    data = await storage.get_object(key)
    try:
        result = await ocr.extract_text(data, ctype, lang)
    except (ocr.OCRUnavailable, ValueError) as exc:
        async with session_scope() as session:
            doc = await session.get(Document, _uuid(document_id))
            if doc:
                doc.ocr_status = ProcessingStatus.FAILED
                doc.error = str(exc)
        raise ApplicationError(str(exc), non_retryable=True) from exc
    async with session_scope() as session:
        doc = await session.get(Document, _uuid(document_id))
        if doc:
            doc.ocr_text = result.text[:2_000_000]
            doc.ocr_confidence = result.confidence
            doc.page_count = result.pages
    return {"chars": len(result.text), "pages": result.pages, "method": result.method}


@activity.defn
async def structure_document_ai(document_id: str) -> dict[str, Any]:
    async with session_scope() as session:
        doc = await session.get(Document, _uuid(document_id))
        if doc is None or not doc.ocr_text:
            return {}
        text, filename = doc.ocr_text, doc.filename
    try:
        fields = await rag.structure_document(text, filename)
    except LLMUnavailable as exc:
        raise ApplicationError("LLM unavailable") from exc
    async with session_scope() as session:
        doc = await session.get(Document, _uuid(document_id))
        if doc:
            doc.extracted_fields = fields
            doc.summary = str(fields.get("summary", ""))[:4000] or None
            detected = str(fields.get("document_type", ""))
            if doc.doc_type == DocumentType.OTHER and detected in {t.value for t in DocumentType}:
                doc.doc_type = DocumentType(detected)
    return fields


@activity.defn
async def index_document(document_id: str) -> int:
    async with session_scope() as session:
        doc = await session.get(Document, _uuid(document_id))
        if doc is None or not doc.ocr_text:
            return 0
        n = await vectorstore.upsert_source(
            source_type="document", source_id=str(doc.id), title=doc.title, text=doc.ocr_text,
            mine_id=str(doc.mine_id) if doc.mine_id else None,
            subsidiary_id=str(doc.subsidiary_id) if doc.subsidiary_id else None,
            extra={"doc_type": doc.doc_type.value},
        )
        doc.embedded_chunks = n
        return n


@activity.defn
async def finish_document(document_id: str, ok: bool, error: str | None) -> None:
    async with session_scope() as session:
        doc = await session.get(Document, _uuid(document_id))
        if doc is None:
            return
        doc.ocr_status = ProcessingStatus.COMPLETED if ok else ProcessingStatus.FAILED
        if error:
            doc.error = error[:2000]
        record_event(
            session, "document.processed" if ok else "document.failed", entity_type="document", entity_id=doc.id,
            actor=None, mine_id=doc.mine_id, subsidiary_id=doc.subsidiary_id,
            data={"title": doc.title, "uploaded_by": str(doc.uploaded_by) if doc.uploaded_by else None,
                  "chunks": doc.embedded_chunks, "error": error},
        )


# ================================================================= reports
@activity.defn
async def build_report(report_id: str, with_ai_summary: bool) -> dict[str, Any]:
    async with session_scope() as session:
        report = await session.get(Report, _uuid(report_id))
        if report is None:
            return {"missing": True}
        report.status = ProcessingStatus.PROCESSING
        metrics = await report_svc.aggregate(session, report.scope, report.scope_id, report.period_start, report.period_end)
        label = await report_svc.scope_label(session, report.scope, report.scope_id)
        title = report.title
        period = f"{report.period_start:%d %b %Y} – {report.period_end:%d %b %Y}"
    summary: str | None = None
    if with_ai_summary:
        try:
            summary = await rag.report_narrative(metrics, label, period)
        except LLMUnavailable:
            summary = None
    async with session_scope() as session:
        # Stamp the current audit-chain head so the report is anchored to a verifiable state.
        head = (
            await session.execute(select(AuditLog.hash).order_by(AuditLog.id.desc()).limit(1))
        ).scalar_one_or_none()
    pdf = report_svc.render_pdf(title, label, metrics, summary, head)
    xlsx = report_svc.render_xlsx(title, metrics)
    pdf_key = f"reports/{report_id}.pdf"
    xlsx_key = f"reports/{report_id}.xlsx"
    await storage.put_object(pdf_key, pdf, "application/pdf")
    await storage.put_object(xlsx_key, xlsx, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    async with session_scope() as session:
        report = await session.get(Report, _uuid(report_id))
        if report:
            report.pdf_key, report.xlsx_key = pdf_key, xlsx_key
            report.metrics = metrics
            report.summary = summary
            report.status = ProcessingStatus.COMPLETED
            report.generated_at = datetime.now(UTC)
            record_event(
                session, "report.ready", entity_type="report", entity_id=report.id, actor=None,
                mine_id=report.scope_id if report.scope == ReportScope.MINE else None,
                subsidiary_id=report.scope_id if report.scope == ReportScope.SUBSIDIARY else None,
                data={"title": report.title, "requested_by": str(report.requested_by) if report.requested_by else None,
                      "scheduled": report.scheduled},
            )
    return {"pdf": pdf_key, "xlsx": xlsx_key, "ai_summary": summary is not None}


@activity.defn
async def fail_report(report_id: str, error: str) -> None:
    async with session_scope() as session:
        report = await session.get(Report, _uuid(report_id))
        if report:
            report.status = ProcessingStatus.FAILED
            report.error = error[:2000]


@activity.defn
async def create_scheduled_reports(period_end_iso: str | None = None) -> list[str]:
    """Create the previous calendar month's national + per-subsidiary reports."""
    today = date.fromisoformat(period_end_iso) if period_end_iso else datetime.now(UTC).date()
    first_this = today.replace(day=1)
    end = first_this - timedelta(days=1)
    start = end.replace(day=1)
    ids: list[str] = []
    async with session_scope() as session:
        subs = (await session.execute(select(Subsidiary))).scalars().all()
        targets: list[tuple[ReportScope, uuid.UUID | None, str]] = [(ReportScope.NATIONAL, None, "All subsidiaries (National)")]
        targets += [(ReportScope.SUBSIDIARY, s.id, f"{s.name} ({s.code})") for s in subs]
        for scope, scope_id, label in targets:
            exists = (
                await session.execute(
                    select(Report.id).where(Report.scope == scope, Report.scope_id.is_(scope_id) if scope_id is None
                                            else Report.scope_id == scope_id,
                                            Report.period_start == start, Report.period_end == end,
                                            Report.scheduled.is_(True))
                )
            ).first()
            if exists:
                continue
            r = Report(title=f"Monthly Statutory Compliance Report — {label} — {start:%B %Y}", scope=scope,
                       scope_id=scope_id, period_start=start, period_end=end, scheduled=True)
            session.add(r)
            await session.flush()
            r.workflow_id = report_svc.report_workflow_id(r.id)
            ids.append(str(r.id))
    return ids


# =============================================================== analytics
@activity.defn
async def train_risk_model() -> dict[str, Any]:
    async with session_scope() as session:
        return await analytics_svc.train_risk_model(session)


@activity.defn
async def recompute_all_risk() -> dict[str, Any]:
    async with session_scope() as session:
        return await analytics_svc.recompute_risk(session)


@activity.defn
async def detect_anomalies() -> dict[str, int]:
    async with session_scope() as session:
        return await analytics_svc.detect_all(session)


@activity.defn
async def index_regulations(force: bool = False) -> int:
    await vectorstore.ensure_collection()
    async with session_scope() as session:
        stmt = select(Regulation)
        if not force:
            stmt = stmt.where(Regulation.is_embedded.is_(False))
        regs = (await session.execute(stmt)).scalars().all()
        count = 0
        for reg in regs:
            await vectorstore.upsert_source(
                source_type="regulation", source_id=str(reg.id),
                title=f"{reg.act} — {reg.section or reg.code}: {reg.title}",
                text=reg.text, category=reg.category.value, extra={"code": reg.code, "act": reg.act},
            )
            reg.is_embedded = True
            count += 1
            activity.heartbeat(count)
        return count


@activity.defn
async def reconcile_pending() -> dict[str, list[str]]:
    """Find documents/reports stuck in PENDING and open grievances (e.g. events lost before Temporal was up)."""
    cutoff = datetime.now(UTC) - timedelta(minutes=15)
    async with session_scope() as session:
        docs = (
            await session.execute(select(Document.id).where(Document.ocr_status == ProcessingStatus.PENDING,
                                                            Document.created_at < cutoff))
        ).scalars().all()
        reports = (
            await session.execute(select(Report.id).where(Report.status == ProcessingStatus.PENDING,
                                                          Report.created_at < cutoff))
        ).scalars().all()
        from app.models import Grievance
        from app.services.grievances import ACTIVE as GRIEVANCE_ACTIVE

        # Every open grievance should have a running SLA timer; starting one that exists is a no-op.
        grievances = (
            await session.execute(select(Grievance.id).where(Grievance.status.in_(GRIEVANCE_ACTIVE)))
        ).scalars().all()
    return {"documents": [str(d) for d in docs], "reports": [str(r) for r in reports],
            "grievances": [str(g) for g in grievances]}


# ================================================================ grievances
@activity.defn
async def escalate_grievance_if_overdue(grievance_id: str) -> dict[str, Any]:
    """Loads the grievance and escalates it when it is past its resolution deadline."""
    from app.services import grievances as grievance_svc

    async with session_scope() as session:
        state = await grievance_svc.escalate_if_overdue(session, _uuid(grievance_id), get_settings().max_escalation_level)
    if state.get("exists") and state.get("escalated"):
        ESCALATIONS.labels("grievance", str(state["level"])).inc()
    return state


ALL_ACTIVITIES = [
    load_violation_state, classify_violation_ai, index_violation, escalate_violation, mark_actions_overdue,
    remind_verification_pending, refresh_mine_risk, load_compliance_state, send_compliance_reminder,
    escalate_overdue_compliance, compliance_sweep, ocr_inspection_attachments, summarize_inspection_ai,
    create_ai_violations, index_inspection, finish_inspection_processing, digitize_document, structure_document_ai,
    index_document, finish_document, build_report, fail_report, create_scheduled_reports, train_risk_model,
    recompute_all_risk, detect_anomalies, index_regulations, reconcile_pending, escalate_grievance_if_overdue,
]
