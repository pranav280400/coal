"""Inspections, violations, corrective actions, attendance and offline ingest."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, File, Form, Query, UploadFile, status
from pydantic import BaseModel

from app.ai import vectorstore
from app.api.deps import DB, CurrentPrincipal, CurrentUser, Paging
from app.core import storage
from app.core.config import get_settings
from app.core.errors import Forbidden, NotFound, ServiceUnavailable
from app.core.metrics import INGEST_EVENTS
from app.models import CorrectiveAction, MediaFile
from app.models.enums import (
    ActionStatus,
    ComplianceCategory,
    InspectionOutcome,
    InspectionType,
    Severity,
    ViolationKind,
    ViolationStatus,
)
from app.schemas.common import Page
from app.schemas.field import (
    ActionCreate,
    ActionOut,
    ActionSubmit,
    ActionVerify,
    AttendanceCreate,
    AttendanceOut,
    IngestBatch,
    IngestResult,
    InspectionCreate,
    InspectionDetail,
    InspectionOut,
    InspectionReview,
    MediaOut,
    SimilarItem,
    ViolationClose,
    ViolationConfirm,
    ViolationCreate,
    ViolationOut,
)
from app.services import contractors as contractor_svc
from app.services import ingest as ingest_svc
from app.services import inspections as inspection_svc
from app.services import media as media_svc
from app.services import violations as violation_svc
from app.services.access import Perm, visible_mine_ids

router = APIRouter(tags=["field operations"])


# ------------------------------------------------------------ inspections
@router.get("/inspections", response_model=Page[InspectionOut])
async def list_inspections(
    session: DB, principal: CurrentPrincipal, paging: Paging,
    mine_id: uuid.UUID | None = None, outcome: InspectionOutcome | None = None,
    inspection_type: InspectionType | None = None, q: str | None = Query(None, max_length=200),
    date_from: datetime | None = None, date_to: datetime | None = None,
) -> Page[InspectionOut]:
    rows, total = await inspection_svc.list_inspections(
        session, principal, mine_id=mine_id, outcome=outcome, inspection_type=inspection_type, q=q,
        date_from=date_from, date_to=date_to, offset=paging.offset, limit=paging.size,
    )
    return Page(items=[InspectionOut.model_validate(r) for r in rows], total=total, page=paging.page, size=paging.size)


@router.post("/inspections", response_model=InspectionOut, status_code=status.HTTP_201_CREATED)
async def create_inspection(body: InspectionCreate, session: DB, principal: CurrentPrincipal) -> InspectionOut:
    inspection, _ = await inspection_svc.create_inspection(session, principal, body)
    return InspectionOut.model_validate(await inspection_svc.get_inspection(session, principal, inspection.id))


@router.get("/inspections/{inspection_id}", response_model=InspectionDetail)
async def get_inspection(inspection_id: uuid.UUID, session: DB, principal: CurrentPrincipal) -> InspectionDetail:
    inspection = await inspection_svc.get_inspection(session, principal, inspection_id)
    detail = InspectionDetail.model_validate(inspection)
    detail.media = [MediaOut.model_validate(m) for m in await media_svc.list_media(session, "inspection", inspection.id)]
    detail.violations = [ViolationOut.model_validate(v) for v in await inspection_svc.violations_for(session, inspection.id)]
    return detail


@router.post("/inspections/{inspection_id}/review", response_model=InspectionOut)
async def review_inspection(
    inspection_id: uuid.UUID, body: InspectionReview, session: DB, principal: CurrentPrincipal
) -> InspectionOut:
    return InspectionOut.model_validate(await inspection_svc.review_inspection(session, principal, inspection_id, body))


async def _entity_mine(session: DB, principal: CurrentPrincipal, entity_type: str, entity_id: uuid.UUID) -> None:
    """Authorise access to the parent entity before touching its media."""
    if entity_type == "inspection":
        await inspection_svc.get_inspection(session, principal, entity_id)
    elif entity_type == "violation":
        await violation_svc.get_violation(session, principal, entity_id)
    elif entity_type == "corrective_action":
        await violation_svc.get_action(session, principal, entity_id)
    else:
        raise NotFound("Unknown entity")


@router.post("/media/{entity_type}/{entity_id}", response_model=MediaOut, status_code=status.HTTP_201_CREATED)
async def upload_media(
    entity_type: str,
    entity_id: uuid.UUID,
    session: DB,
    principal: CurrentPrincipal,
    file: Annotated[UploadFile, File(...)],
    latitude: Annotated[float | None, Form(ge=-90, le=90)] = None,
    longitude: Annotated[float | None, Form(ge=-180, le=180)] = None,
    captured_at: Annotated[datetime | None, Form()] = None,
) -> MediaOut:
    await _entity_mine(session, principal, entity_type, entity_id)
    if not (principal.can(Perm.INSPECTION_WRITE) or principal.can(Perm.ACTION_EXECUTE) or principal.can(Perm.VIOLATION_WRITE)):
        raise Forbidden("Your role cannot upload evidence")
    media = await media_svc.attach_media(
        session, entity_type=entity_type, entity_id=entity_id, upload=file, uploaded_by=principal.id,
        latitude=latitude, longitude=longitude, captured_at=captured_at,
    )
    await session.commit()
    return MediaOut.model_validate(media)


@router.get("/media/{entity_type}/{entity_id}", response_model=list[MediaOut])
async def list_media(entity_type: str, entity_id: uuid.UUID, session: DB, principal: CurrentPrincipal) -> list[MediaOut]:
    await _entity_mine(session, principal, entity_type, entity_id)
    return [MediaOut.model_validate(m) for m in await media_svc.list_media(session, entity_type, entity_id)]


class SignedUrl(BaseModel):
    url: str
    expires_in: int


@router.get("/media-files/{media_id}/url", response_model=SignedUrl)
async def media_url(media_id: uuid.UUID, session: DB, principal: CurrentPrincipal) -> SignedUrl:
    media = await session.get(MediaFile, media_id)
    if media is None:
        raise NotFound("File not found")
    await _entity_mine(session, principal, media.entity_type, media.entity_id)
    return SignedUrl(
        url=await storage.presigned_get_url(media.storage_key, media.filename, inline=True),
        expires_in=get_settings().s3_presign_ttl_seconds,
    )


# ------------------------------------------------------------- violations
@router.get("/violations", response_model=Page[ViolationOut])
async def list_violations(
    session: DB, principal: CurrentPrincipal, paging: Paging,
    mine_id: uuid.UUID | None = None, v_status: ViolationStatus | None = Query(None, alias="status"),
    severity: Severity | None = None, category: ComplianceCategory | None = None,
    contractor_id: uuid.UUID | None = None, kind: ViolationKind | None = None,
    q: str | None = Query(None, max_length=200), open_only: bool = False,
) -> Page[ViolationOut]:
    rows, total = await violation_svc.list_violations(
        session, principal, mine_id=mine_id, status=v_status, severity=severity, category=category,
        contractor_id=contractor_id, kind=kind, q=q, open_only=open_only, offset=paging.offset, limit=paging.size,
    )
    return Page(items=[ViolationOut.model_validate(r) for r in rows], total=total, page=paging.page, size=paging.size)


@router.post("/violations", response_model=ViolationOut, status_code=status.HTTP_201_CREATED)
async def create_violation(body: ViolationCreate, session: DB, principal: CurrentPrincipal) -> ViolationOut:
    violation, _ = await violation_svc.create_violation(session, principal, body)
    return ViolationOut.model_validate(await violation_svc.get_violation(session, principal, violation.id))


@router.get("/violations/{violation_id}", response_model=ViolationOut)
async def get_violation(violation_id: uuid.UUID, session: DB, principal: CurrentPrincipal) -> ViolationOut:
    return ViolationOut.model_validate(await violation_svc.get_violation(session, principal, violation_id))


@router.post("/violations/{violation_id}/classify", response_model=ViolationOut)
async def classify_violation(violation_id: uuid.UUID, session: DB, principal: CurrentPrincipal) -> ViolationOut:
    return ViolationOut.model_validate(await violation_svc.reclassify(session, principal, violation_id))


@router.post("/violations/{violation_id}/confirm", response_model=ViolationOut)
async def confirm_violation(
    violation_id: uuid.UUID, body: ViolationConfirm, session: DB, principal: CurrentPrincipal
) -> ViolationOut:
    return ViolationOut.model_validate(await violation_svc.confirm_severity(session, principal, violation_id, body))


@router.post("/violations/{violation_id}/close", response_model=ViolationOut)
async def close_violation(
    violation_id: uuid.UUID, body: ViolationClose, session: DB, principal: CurrentPrincipal
) -> ViolationOut:
    return ViolationOut.model_validate(await violation_svc.close_violation(session, principal, violation_id, body.notes))


@router.get("/violations/{violation_id}/similar", response_model=list[SimilarItem])
async def similar_violations(
    violation_id: uuid.UUID, session: DB, principal: CurrentPrincipal, limit: int = Query(6, ge=1, le=20)
) -> list[SimilarItem]:
    violation = await violation_svc.get_violation(session, principal, violation_id)
    scope = await visible_mine_ids(session, principal)
    try:
        hits = await vectorstore.search(
            f"{violation.title}. {violation.description}",
            visible_mine_ids=[str(m) for m in scope] if scope is not None else None,
            source_types=["violation", "inspection"], limit=limit, exclude_source_id=str(violation.id),
        )
    except Exception as exc:
        raise ServiceUnavailable("Semantic search is currently unavailable") from exc
    return [
        SimilarItem(source_type=h["source_type"], source_id=h["source_id"], title=h["title"],
                    snippet=h["text"][:300], score=round(h["score"], 3), mine_id=h["mine_id"])
        for h in hits
    ]


# ----------------------------------------------------- corrective actions
def _action_out(a: CorrectiveAction) -> ActionOut:
    out = ActionOut.model_validate(a)
    out.violation_number = a.violation.number
    out.violation_title = a.violation.title
    out.mine_name = a.violation.mine.name
    return out


@router.get("/corrective-actions", response_model=Page[ActionOut])
async def list_actions(
    session: DB, principal: CurrentPrincipal, paging: Paging,
    violation_id: uuid.UUID | None = None, a_status: ActionStatus | None = Query(None, alias="status"),
    mine: bool = Query(False, description="Only actions assigned to me"),
) -> Page[ActionOut]:
    rows, total = await violation_svc.list_actions(
        session, principal, violation_id=violation_id, status=a_status, assigned_to_me=mine,
        offset=paging.offset, limit=paging.size,
    )
    return Page(items=[_action_out(a) for a in rows], total=total, page=paging.page, size=paging.size)


@router.post("/corrective-actions", response_model=ActionOut, status_code=status.HTTP_201_CREATED)
async def assign_action(body: ActionCreate, session: DB, principal: CurrentPrincipal) -> ActionOut:
    return _action_out(await violation_svc.assign_action(session, principal, body))


@router.get("/corrective-actions/{action_id}", response_model=ActionOut)
async def get_action(action_id: uuid.UUID, session: DB, principal: CurrentPrincipal) -> ActionOut:
    return _action_out(await violation_svc.get_action(session, principal, action_id))


@router.post("/corrective-actions/{action_id}/start", response_model=ActionOut)
async def start_action(action_id: uuid.UUID, session: DB, principal: CurrentPrincipal) -> ActionOut:
    return _action_out(await violation_svc.start_action(session, principal, action_id))


@router.post("/corrective-actions/{action_id}/submit", response_model=ActionOut)
async def submit_action(action_id: uuid.UUID, body: ActionSubmit, session: DB, principal: CurrentPrincipal) -> ActionOut:
    return _action_out(await violation_svc.submit_action(session, principal, action_id, body))


@router.post("/corrective-actions/{action_id}/verify", response_model=ActionOut)
async def verify_action(action_id: uuid.UUID, body: ActionVerify, session: DB, principal: CurrentPrincipal) -> ActionOut:
    return _action_out(await violation_svc.verify_action(session, principal, action_id, body))


# ------------------------------------------------------------- attendance
@router.get("/attendance", response_model=Page[AttendanceOut])
async def list_attendance(
    session: DB, principal: CurrentPrincipal, paging: Paging,
    mine_id: uuid.UUID | None = None, date_from: datetime | None = None, date_to: datetime | None = None,
) -> Page[AttendanceOut]:
    rows, total = await contractor_svc.list_attendance(
        session, principal, mine_id=mine_id, date_from=date_from, date_to=date_to,
        offset=paging.offset, limit=paging.size,
    )
    return Page(items=[AttendanceOut.model_validate(r) for r in rows], total=total, page=paging.page, size=paging.size)


@router.post("/attendance", response_model=AttendanceOut, status_code=status.HTTP_201_CREATED)
async def log_attendance(body: AttendanceCreate, session: DB, principal: CurrentPrincipal) -> AttendanceOut:
    record, _ = await contractor_svc.log_attendance(session, principal, body)
    return AttendanceOut.model_validate(record)


# ---------------------------------------------------- offline sync ingest
class IngestResponse(BaseModel):
    results: list[IngestResult]


@router.post("/ingest/events", response_model=IngestResponse, status_code=status.HTTP_202_ACCEPTED)
async def ingest_events(body: IngestBatch, user: CurrentUser, session: DB) -> IngestResponse:
    """Accept a batch of offline-captured field events and publish them to Kafka.

    If Kafka is unreachable the batch is processed synchronously instead, so field
    data is never lost to a broker outage.
    """
    from app.main import get_event_producer  # late import avoids a cycle

    s = get_settings()
    producer = await get_event_producer()
    results: list[IngestResult] = []
    for event in body.events:
        envelope = {
            "client_event_id": event.client_event_id,
            "event_type": event.event_type,
            "captured_at": event.captured_at.isoformat(),
            "payload": event.payload,
            "user_id": str(user.id),
            "device_id": body.device_id,
            "received_at": datetime.now().astimezone().isoformat(),
        }
        mine_key = str(event.payload.get("mine_id") or user.mine_id or user.id)
        if producer is not None:
            try:
                await producer.send_and_wait(s.kafka_topic_field_events, envelope, key=mine_key)
                await ingest_svc.set_status(event.client_event_id, "queued")
                INGEST_EVENTS.labels(event.event_type, "queued").inc()
                results.append(IngestResult(client_event_id=event.client_event_id, status="accepted"))
                continue
            except Exception:  # fall through to synchronous processing
                pass
        try:
            status_, etype, eid = await ingest_svc.process(session, user.id, event)
            await ingest_svc.set_status(event.client_event_id, status_, entity_type=etype, entity_id=eid)
            results.append(IngestResult(client_event_id=event.client_event_id, status=status_))  # type: ignore[arg-type]
        except (ValueError, PermissionError) as exc:
            await session.rollback()
            await ingest_svc.set_status(event.client_event_id, "rejected", detail=str(exc))
            results.append(IngestResult(client_event_id=event.client_event_id, status="rejected", detail=str(exc)))
    return IngestResponse(results=results)


@router.get("/ingest/status")
async def ingest_status(user: CurrentUser, ids: Annotated[list[str], Query(max_length=200)]) -> dict:
    return await ingest_svc.get_statuses(ids)
