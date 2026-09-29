from __future__ import annotations

import uuid

from fastapi import APIRouter, Query, status

from app.api.deps import DB, CurrentPrincipal, Paging
from app.models import Contractor
from app.models.enums import ContractorStatus
from app.schemas.common import Page
from app.schemas.contractor import (
    ContractCreate,
    ContractorCreate,
    ContractorDetail,
    ContractorOut,
    ContractorUpdate,
    ContractOut,
)
from app.services import contractors as svc

router = APIRouter(prefix="/contractors", tags=["contractors"])


def _mask_pan(pan: str | None) -> str | None:
    return f"{pan[:2]}XXXXX{pan[-3:]}" if pan and len(pan) == 10 else None


async def _detail(session: DB, contractor: Contractor) -> ContractorDetail:
    open_v, total_v = await svc.violation_counts(session, contractor.id)
    detail = ContractorDetail.model_validate(contractor)
    detail.pan_masked = _mask_pan(contractor.pan)
    detail.contracts = [ContractOut.model_validate(c) for c in contractor.contracts]
    detail.open_violations = open_v
    detail.total_violations = total_v
    return detail


@router.get("", response_model=Page[ContractorOut])
async def list_contractors(
    session: DB, principal: CurrentPrincipal, paging: Paging,
    c_status: ContractorStatus | None = Query(None, alias="status"), q: str | None = Query(None, max_length=200),
) -> Page[ContractorOut]:
    rows, total = await svc.list_contractors(session, principal, status=c_status, q=q,
                                             offset=paging.offset, limit=paging.size)
    return Page(items=[ContractorOut.model_validate(r) for r in rows], total=total, page=paging.page, size=paging.size)


@router.post("", response_model=ContractorDetail, status_code=status.HTTP_201_CREATED)
async def create_contractor(body: ContractorCreate, session: DB, principal: CurrentPrincipal) -> ContractorDetail:
    return await _detail(session, await svc.create_contractor(session, principal, body))


@router.get("/{contractor_id}", response_model=ContractorDetail)
async def get_contractor(contractor_id: uuid.UUID, session: DB, principal: CurrentPrincipal) -> ContractorDetail:
    return await _detail(session, await svc.get_contractor(session, principal, contractor_id))


@router.patch("/{contractor_id}", response_model=ContractorDetail)
async def update_contractor(
    contractor_id: uuid.UUID, body: ContractorUpdate, session: DB, principal: CurrentPrincipal
) -> ContractorDetail:
    return await _detail(session, await svc.update_contractor(session, principal, contractor_id, body))


@router.post("/{contractor_id}/verify", response_model=ContractorDetail)
async def verify_contractor(contractor_id: uuid.UUID, session: DB, principal: CurrentPrincipal) -> ContractorDetail:
    return await _detail(session, await svc.verify_contractor(session, principal, contractor_id))


@router.post("/{contractor_id}/contracts", response_model=ContractOut, status_code=status.HTTP_201_CREATED)
async def add_contract(
    contractor_id: uuid.UUID, body: ContractCreate, session: DB, principal: CurrentPrincipal
) -> ContractOut:
    return ContractOut.model_validate(await svc.add_contract(session, principal, contractor_id, body))
