from __future__ import annotations

import uuid
from datetime import date

from fastapi import APIRouter, Query, Response, status

from app.api.deps import DB, CurrentPrincipal, Paging
from app.models.enums import ComplianceCategory, ComplianceStatus
from app.schemas.common import Page
from app.schemas.compliance import (
    ComplianceComplete,
    ComplianceCreate,
    ComplianceOut,
    ComplianceSummary,
    ComplianceUpdate,
)
from app.services import compliance as svc

router = APIRouter(prefix="/compliance", tags=["compliance"])


@router.get("", response_model=Page[ComplianceOut])
async def list_items(
    session: DB, principal: CurrentPrincipal, paging: Paging,
    mine_id: uuid.UUID | None = None, category: ComplianceCategory | None = None,
    item_status: ComplianceStatus | None = Query(None, alias="status"),
    due_before: date | None = None, q: str | None = Query(None, max_length=200),
) -> Page[ComplianceOut]:
    rows, total = await svc.list_items(
        session, principal, mine_id=mine_id, category=category, status=item_status, due_before=due_before, q=q,
        offset=paging.offset, limit=paging.size,
    )
    return Page(items=[ComplianceOut.model_validate(r) for r in rows], total=total, page=paging.page, size=paging.size)


@router.get("/summary", response_model=ComplianceSummary)
async def summary(session: DB, principal: CurrentPrincipal, mine_id: uuid.UUID | None = None) -> ComplianceSummary:
    return ComplianceSummary.model_validate(await svc.summary(session, principal, mine_id))


@router.post("", response_model=ComplianceOut, status_code=status.HTTP_201_CREATED)
async def create_item(body: ComplianceCreate, session: DB, principal: CurrentPrincipal) -> ComplianceOut:
    return ComplianceOut.model_validate(await svc.create_item(session, principal, body))


@router.get("/{item_id}", response_model=ComplianceOut)
async def get_item(item_id: uuid.UUID, session: DB, principal: CurrentPrincipal) -> ComplianceOut:
    return ComplianceOut.model_validate(await svc.get_item(session, principal, item_id))


@router.patch("/{item_id}", response_model=ComplianceOut)
async def update_item(item_id: uuid.UUID, body: ComplianceUpdate, session: DB, principal: CurrentPrincipal) -> ComplianceOut:
    return ComplianceOut.model_validate(await svc.update_item(session, principal, item_id, body))


@router.post("/{item_id}/complete", response_model=ComplianceOut)
async def complete_item(
    item_id: uuid.UUID, body: ComplianceComplete, session: DB, principal: CurrentPrincipal
) -> ComplianceOut:
    return ComplianceOut.model_validate(await svc.complete_item(session, principal, item_id, body))


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_item(item_id: uuid.UUID, session: DB, principal: CurrentPrincipal) -> Response:
    await svc.delete_item(session, principal, item_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
