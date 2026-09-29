"""Documents, reports, analytics, dashboard, audit trail and global search."""

from __future__ import annotations

import uuid
from typing import Annotated, Any, Literal

from fastapi import APIRouter, File, Form, Query, UploadFile, status
from pydantic import BaseModel
from sqlalchemy import func, or_, select

from app.api.deps import DB, CurrentPrincipal, Paging, require
from app.api.v1.field import SignedUrl
from app.core import storage
from app.core.config import get_settings
from app.core.errors import InvalidState, NotFound
from app.models import Anomaly, AuditLog, Contractor, Inspection, Mine, Regulation, Report, Violation
from app.models.enums import AnomalyKind, AnomalyStatus, DocumentType, ProcessingStatus
from app.schemas.common import Page
from app.schemas.governance import (
    AnomalyOut,
    AuditOut,
    AuditVerifyResult,
    DocumentDetail,
    DocumentOut,
    ReportCreate,
    ReportOut,
    RiskEntry,
)
from app.services import analytics as analytics_svc
from app.services import audit as audit_svc
from app.services import dashboard as dashboard_svc
from app.services import documents as document_svc
from app.services import reports as report_svc
from app.services.access import Perm, Principal, scope_mines
from app.services.events import record_event
from app.workflows import client as temporal

router = APIRouter(tags=["governance"])


# -------------------------------------------------------------- dashboard
@router.get("/dashboard/summary")
async def dashboard_summary(session: DB, principal: CurrentPrincipal, fresh: bool = False) -> dict[str, Any]:
    return await dashboard_svc.get_summary(session, principal, fresh=fresh)


# -------------------------------------------------------------- documents
@router.get("/documents", response_model=Page[DocumentOut])
async def list_documents(
    session: DB, principal: CurrentPrincipal, paging: Paging,
    mine_id: uuid.UUID | None = None, doc_type: DocumentType | None = None,
    ocr_status: ProcessingStatus | None = Query(None, alias="status"), q: str | None = Query(None, max_length=200),
) -> Page[DocumentOut]:
    rows, total = await document_svc.list_documents(
        session, principal, mine_id=mine_id, doc_type=doc_type, status=ocr_status, q=q,
        offset=paging.offset, limit=paging.size,
    )
    return Page(items=[DocumentOut.model_validate(d) for d in rows], total=total, page=paging.page, size=paging.size)


@router.post("/documents", response_model=DocumentOut, status_code=status.HTTP_201_CREATED)
async def upload_document(
    session: DB,
    principal: CurrentPrincipal,
    file: Annotated[UploadFile, File(...)],
    title: Annotated[str, Form(min_length=2, max_length=300)],
    doc_type: Annotated[DocumentType, Form()] = DocumentType.OTHER,
    mine_id: Annotated[uuid.UUID | None, Form()] = None,
    language: Annotated[str, Form(pattern=r"^[a-z]{3}(\+[a-z]{3})*$")] = "eng+hin",
) -> DocumentOut:
    doc = await document_svc.upload_document(
        session, principal, upload=file, title=title, doc_type=doc_type, mine_id=mine_id, language=language
    )
    return DocumentOut.model_validate(doc)


@router.get("/documents/{document_id}", response_model=DocumentDetail)
async def get_document(document_id: uuid.UUID, session: DB, principal: CurrentPrincipal) -> DocumentDetail:
    return DocumentDetail.model_validate(await document_svc.get_document(session, principal, document_id))


@router.get("/documents/{document_id}/download", response_model=SignedUrl)
async def download_document(document_id: uuid.UUID, session: DB, principal: CurrentPrincipal) -> SignedUrl:
    doc = await document_svc.get_document(session, principal, document_id)
    return SignedUrl(url=await storage.presigned_get_url(doc.storage_key, doc.filename),
                     expires_in=get_settings().s3_presign_ttl_seconds)


@router.post("/documents/{document_id}/reprocess", response_model=DocumentOut)
async def reprocess_document(document_id: uuid.UUID, session: DB, principal: CurrentPrincipal) -> DocumentOut:
    principal.require(Perm.DOCUMENT_WRITE)
    doc = await document_svc.get_document(session, principal, document_id)
    if doc.ocr_status == ProcessingStatus.PROCESSING:
        raise InvalidState("Document is already being processed")
    doc.ocr_status = ProcessingStatus.PENDING
    doc.error = None
    doc.workflow_id = f"{document_svc.digitize_workflow_id(doc.id)}-r{uuid.uuid4().hex[:6]}"
    # The orchestrator consumer starts the workflow from this event (durable via the outbox).
    record_event(session, "document.reprocess_requested", entity_type="document", entity_id=doc.id,
                 actor=principal, mine_id=doc.mine_id, data={"workflow_id": doc.workflow_id})
    await session.commit()
    return DocumentOut.model_validate(doc)


# ---------------------------------------------------------------- reports
def _report_out(r: Report) -> ReportOut:
    out = ReportOut.model_validate(r)
    out.has_pdf = bool(r.pdf_key)
    out.has_xlsx = bool(r.xlsx_key)
    return out


@router.get("/reports", response_model=Page[ReportOut])
async def list_reports(session: DB, principal: CurrentPrincipal, paging: Paging) -> Page[ReportOut]:
    stmt = report_svc.report_query(principal)
    total = (await session.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    rows = (await session.execute(stmt.order_by(Report.created_at.desc()).offset(paging.offset).limit(paging.size))).scalars().all()
    return Page(items=[_report_out(r) for r in rows], total=total, page=paging.page, size=paging.size)


@router.post("/reports", response_model=ReportOut, status_code=status.HTTP_202_ACCEPTED)
async def request_report(body: ReportCreate, session: DB, principal: CurrentPrincipal) -> ReportOut:
    # Workflow is started by the orchestrator consumer from the "report.requested" event.
    return _report_out(await report_svc.create_request(session, principal, body))


@router.get("/reports/{report_id}", response_model=ReportOut)
async def get_report(report_id: uuid.UUID, session: DB, principal: CurrentPrincipal) -> ReportOut:
    return _report_out(await report_svc.get_report(session, principal, report_id))


@router.get("/reports/{report_id}/download", response_model=SignedUrl)
async def download_report(
    report_id: uuid.UUID, session: DB, principal: CurrentPrincipal, fmt: Literal["pdf", "xlsx"] = Query("pdf", alias="format")
) -> SignedUrl:
    report = await report_svc.get_report(session, principal, report_id)
    key = report.pdf_key if fmt == "pdf" else report.xlsx_key
    if not key:
        raise NotFound("Report file is not ready yet")
    filename = f"Lumen_{report.scope.value}_{report.period_start:%Y%m%d}_{report.period_end:%Y%m%d}.{fmt}"
    return SignedUrl(url=await storage.presigned_get_url(key, filename), expires_in=get_settings().s3_presign_ttl_seconds)


# -------------------------------------------------------------- analytics
@router.get("/analytics/risk", response_model=list[RiskEntry])
async def risk_ranking(
    session: DB, principal: CurrentPrincipal,
    entity_type: Literal["mine", "contractor"] = "mine", limit: int = Query(20, ge=1, le=200),
) -> list[RiskEntry]:
    return [RiskEntry.model_validate(e) for e in await analytics_svc.risk_ranking(session, principal, entity_type, limit)]


@router.get("/analytics/risk/{entity_id}/history")
async def risk_history(entity_id: uuid.UUID, session: DB, principal: CurrentPrincipal) -> list[dict[str, Any]]:
    return await analytics_svc.risk_history(session, entity_id)


@router.post("/analytics/recompute", status_code=status.HTTP_202_ACCEPTED)
async def recompute(principal: Principal = require(Perm.ANALYTICS_RUN)) -> dict[str, str]:
    handle = await temporal.start_workflow(
        "RiskAnalyticsWorkflow", {"train": True}, workflow_id=f"risk-analytics-manual-{uuid.uuid4().hex[:8]}"
    )
    return {"workflow_id": handle.id if handle else "already-running"}


@router.get("/analytics/categories")
async def category_breakdown(session: DB, principal: CurrentPrincipal, days: int = Query(365, ge=7, le=1825)) -> list[dict[str, Any]]:
    return await analytics_svc.category_breakdown(session, principal, days)


@router.get("/analytics/trends")
async def trends(session: DB, principal: CurrentPrincipal, months: int = Query(12, ge=3, le=36)) -> list[dict[str, Any]]:
    return await dashboard_svc.violation_trends(session, principal, months)


@router.get("/analytics/anomalies", response_model=Page[AnomalyOut])
async def anomalies(
    session: DB, principal: CurrentPrincipal, paging: Paging,
    a_status: AnomalyStatus | None = Query(None, alias="status"), kind: AnomalyKind | None = None,
) -> Page[AnomalyOut]:
    stmt = scope_mines(select(Anomaly), principal, Anomaly.mine_id)
    if a_status:
        stmt = stmt.where(Anomaly.status == a_status)
    if kind:
        stmt = stmt.where(Anomaly.kind == kind)
    total = (await session.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    rows = (await session.execute(stmt.order_by(Anomaly.detected_at.desc()).offset(paging.offset).limit(paging.size))).scalars().all()
    return Page(items=[AnomalyOut.model_validate(a) for a in rows], total=total, page=paging.page, size=paging.size)


class AnomalyUpdate(BaseModel):
    status: Literal["acknowledged", "resolved"]


@router.post("/analytics/anomalies/{anomaly_id}", response_model=AnomalyOut)
async def update_anomaly(anomaly_id: uuid.UUID, body: AnomalyUpdate, session: DB, principal: CurrentPrincipal) -> AnomalyOut:
    principal.require(Perm.VIOLATION_CONFIRM)
    stmt = scope_mines(select(Anomaly).where(Anomaly.id == anomaly_id), principal, Anomaly.mine_id)
    anomaly = (await session.execute(stmt)).scalars().first()
    if anomaly is None:
        raise NotFound("Anomaly not found")
    anomaly.status = AnomalyStatus(body.status)
    anomaly.acknowledged_by = principal.id
    await session.commit()
    return AnomalyOut.model_validate(anomaly)


# ------------------------------------------------------------------ audit
@router.get("/audit", response_model=Page[AuditOut])
async def audit_log(
    session: DB, paging: Paging, principal: Principal = require(Perm.AUDIT_READ),
    entity_type: str | None = Query(None, max_length=48), entity_id: str | None = Query(None, max_length=64),
    action: str | None = Query(None, max_length=64), actor_id: uuid.UUID | None = None,
) -> Page[AuditOut]:
    stmt = select(AuditLog)
    if not principal.is_global:
        visible = scope_mines(select(Mine.id), principal, Mine.id)
        stmt = stmt.where(or_(AuditLog.mine_id.in_(visible), AuditLog.subsidiary_id == principal.subsidiary_id))
    if entity_type:
        stmt = stmt.where(AuditLog.entity_type == entity_type)
    if entity_id:
        stmt = stmt.where(AuditLog.entity_id == entity_id)
    if action:
        stmt = stmt.where(AuditLog.action.ilike(f"{action}%"))
    if actor_id:
        stmt = stmt.where(AuditLog.actor_id == actor_id)
    total = (await session.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    rows = (await session.execute(stmt.order_by(AuditLog.id.desc()).offset(paging.offset).limit(paging.size))).scalars().all()
    return Page(items=[AuditOut.model_validate(r) for r in rows], total=total, page=paging.page, size=paging.size)


@router.get("/audit/entity/{entity_type}/{entity_id}", response_model=list[AuditOut])
async def entity_timeline(entity_type: str, entity_id: str, session: DB, principal: CurrentPrincipal) -> list[AuditOut]:
    """Timeline of one record (visible to anyone who can read the record itself)."""
    if entity_type == "violation":
        from app.services.violations import get_violation

        await get_violation(session, principal, uuid.UUID(entity_id))
    elif entity_type == "inspection":
        from app.services.inspections import get_inspection

        await get_inspection(session, principal, uuid.UUID(entity_id))
    elif entity_type == "compliance_item":
        from app.services.compliance import get_item

        await get_item(session, principal, uuid.UUID(entity_id))
    elif entity_type == "corrective_action":
        from app.services.violations import get_action

        await get_action(session, principal, uuid.UUID(entity_id))
    elif entity_type == "document":
        await document_svc.get_document(session, principal, uuid.UUID(entity_id))
    elif entity_type == "contractor":
        from app.services.contractors import get_contractor

        await get_contractor(session, principal, uuid.UUID(entity_id))
    elif entity_type == "grievance":
        from app.services.grievances import get_grievance

        await get_grievance(session, principal, uuid.UUID(entity_id))
    elif not principal.can(Perm.AUDIT_READ):
        raise NotFound("Not found")
    rows = (
        await session.execute(
            select(AuditLog).where(AuditLog.entity_type == entity_type, AuditLog.entity_id == entity_id)
            .order_by(AuditLog.id)
        )
    ).scalars().all()
    return [AuditOut.model_validate(r) for r in rows]


@router.get("/audit/verify", response_model=AuditVerifyResult)
async def verify_audit(session: DB, principal: Principal = require(Perm.AUDIT_READ)) -> AuditVerifyResult:
    return AuditVerifyResult.model_validate(await audit_svc.verify_chain(session))


# ----------------------------------------------------------------- search
@router.get("/search")
async def global_search(session: DB, principal: CurrentPrincipal, q: str = Query(..., min_length=2, max_length=100)) -> dict[str, Any]:
    like = f"%{q}%"
    mines = (await session.execute(
        scope_mines(select(Mine).where(or_(Mine.name.ilike(like), Mine.code.ilike(like))), principal, Mine.id).limit(5)
    )).scalars().unique().all()
    inspections = (await session.execute(
        scope_mines(select(Inspection).where(Inspection.title.ilike(like)), principal, Inspection.mine_id)
        .order_by(Inspection.inspected_at.desc()).limit(5)
    )).scalars().unique().all()
    violations = (await session.execute(
        scope_mines(select(Violation).where(Violation.title.ilike(like)), principal, Violation.mine_id)
        .order_by(Violation.occurred_at.desc()).limit(5)
    )).scalars().unique().all()
    from app.services.contractors import base_query as contractor_query

    contractors = (await session.execute(
        contractor_query(principal).where(or_(Contractor.name.ilike(like), Contractor.registration_no.ilike(like))).limit(5)
    )).scalars().unique().all()
    regulations = (await session.execute(
        select(Regulation).where(or_(Regulation.title.ilike(like), Regulation.code.ilike(like))).limit(5)
    )).scalars().all()
    return {
        "mines": [{"id": str(m.id), "title": m.name, "subtitle": f"{m.code} · {m.subsidiary.code}", "href": f"/map?mine={m.id}"} for m in mines],
        "inspections": [{"id": str(i.id), "title": i.title, "subtitle": f"INS-{i.number} · {i.mine.name}", "href": f"/inspections/{i.id}"} for i in inspections],
        "violations": [{"id": str(v.id), "title": v.title, "subtitle": f"VIO-{v.number} · {v.severity.value}", "href": f"/violations/{v.id}"} for v in violations],
        "contractors": [{"id": str(c.id), "title": c.name, "subtitle": c.registration_no, "href": f"/contractors/{c.id}"} for c in contractors],
        "regulations": [{"id": str(r.id), "title": r.title, "subtitle": f"{r.act} · {r.section or r.code}", "href": f"/compliance?regulation={r.code}"} for r in regulations],
    }

