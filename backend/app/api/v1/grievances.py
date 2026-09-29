from __future__ import annotations

import uuid

from fastapi import APIRouter, Query, status

from app.api.deps import DB, CurrentPrincipal, Paging
from app.models.enums import GrievanceCategory, GrievanceStatus
from app.schemas.common import Page
from app.schemas.grievance import (
    GrievanceAssign,
    GrievanceClose,
    GrievanceCreate,
    GrievanceOut,
    GrievanceReject,
    GrievanceReopen,
    GrievanceResolve,
    GrievanceSummary,
)
from app.services import grievances as svc

router = APIRouter(prefix="/grievances", tags=["grievances"])


@router.get("", response_model=Page[GrievanceOut])
async def list_grievances(
    session: DB, principal: CurrentPrincipal, paging: Paging,
    view: str = Query("all", pattern=r"^(all|raised|assigned)$"),
    g_status: GrievanceStatus | None = Query(None, alias="status"),
    category: GrievanceCategory | None = None, mine_id: uuid.UUID | None = None, overdue: bool = False,
    q: str | None = Query(None, max_length=200),
) -> Page[GrievanceOut]:
    rows, total = await svc.list_grievances(
        session, principal, view=view, status=g_status, category=category, mine_id=mine_id, overdue=overdue, q=q,
        offset=paging.offset, limit=paging.size,
    )
    return Page(items=[svc.to_out(g, principal) for g in rows], total=total, page=paging.page, size=paging.size)


@router.get("/summary", response_model=GrievanceSummary)
async def summary(session: DB, principal: CurrentPrincipal, mine_id: uuid.UUID | None = None) -> GrievanceSummary:
    return GrievanceSummary.model_validate(await svc.summary(session, principal, mine_id))


@router.post("", response_model=GrievanceOut, status_code=status.HTTP_201_CREATED)
async def create(body: GrievanceCreate, session: DB, principal: CurrentPrincipal) -> GrievanceOut:
    return svc.to_out(await svc.create_grievance(session, principal, body), principal)


@router.get("/{grievance_id}", response_model=GrievanceOut)
async def get(grievance_id: uuid.UUID, session: DB, principal: CurrentPrincipal) -> GrievanceOut:
    return svc.to_out(await svc.get_grievance(session, principal, grievance_id), principal)


@router.post("/{grievance_id}/assign", response_model=GrievanceOut)
async def assign(grievance_id: uuid.UUID, body: GrievanceAssign, session: DB, principal: CurrentPrincipal) -> GrievanceOut:
    return svc.to_out(await svc.assign(session, principal, grievance_id, body), principal)


@router.post("/{grievance_id}/start", response_model=GrievanceOut)
async def start(grievance_id: uuid.UUID, session: DB, principal: CurrentPrincipal) -> GrievanceOut:
    return svc.to_out(await svc.start(session, principal, grievance_id), principal)


@router.post("/{grievance_id}/resolve", response_model=GrievanceOut)
async def resolve(grievance_id: uuid.UUID, body: GrievanceResolve, session: DB, principal: CurrentPrincipal) -> GrievanceOut:
    return svc.to_out(await svc.resolve(session, principal, grievance_id, body), principal)


@router.post("/{grievance_id}/reject", response_model=GrievanceOut)
async def reject(grievance_id: uuid.UUID, body: GrievanceReject, session: DB, principal: CurrentPrincipal) -> GrievanceOut:
    return svc.to_out(await svc.reject(session, principal, grievance_id, body), principal)


@router.post("/{grievance_id}/close", response_model=GrievanceOut)
async def close(grievance_id: uuid.UUID, body: GrievanceClose, session: DB, principal: CurrentPrincipal) -> GrievanceOut:
    return svc.to_out(await svc.close(session, principal, grievance_id, body), principal)


@router.post("/{grievance_id}/reopen", response_model=GrievanceOut)
async def reopen(grievance_id: uuid.UUID, body: GrievanceReopen, session: DB, principal: CurrentPrincipal) -> GrievanceOut:
    return svc.to_out(await svc.reopen(session, principal, grievance_id, body), principal)
