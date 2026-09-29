from __future__ import annotations

import uuid

from fastapi import APIRouter, Query, status

from app.api.deps import DB, CurrentPrincipal, Paging
from app.models.enums import EnvParameter
from app.schemas.common import Page
from app.schemas.operations import (
    EnvLimit,
    EnvReadingCreate,
    EnvReadingOut,
    EnvSummary,
    EnvTrendPoint,
    ProductionOut,
    ProductionSummary,
    ProductionUpsert,
)
from app.services import operations as svc

router = APIRouter(tags=["operations"])


# ---------------------------------------------------------------- production
@router.get("/production", response_model=Page[ProductionOut])
async def list_production(
    session: DB, principal: CurrentPrincipal, paging: Paging, mine_id: uuid.UUID | None = None,
) -> Page[ProductionOut]:
    rows, total = await svc.list_production(session, principal, mine_id=mine_id, offset=paging.offset,
                                            limit=paging.size)
    return Page(items=[ProductionOut.model_validate(r) for r in rows], total=total, page=paging.page, size=paging.size)


@router.get("/production/summary", response_model=ProductionSummary)
async def production_summary(
    session: DB, principal: CurrentPrincipal, mine_id: uuid.UUID | None = None,
    months: int = Query(12, ge=3, le=36),
) -> ProductionSummary:
    return ProductionSummary.model_validate(await svc.production_summary(session, principal, mine_id, months))


@router.put("/production", response_model=ProductionOut)
async def upsert_production(body: ProductionUpsert, session: DB, principal: CurrentPrincipal) -> ProductionOut:
    """Create or correct the monthly return for a mine (one per mine per month)."""
    return ProductionOut.model_validate(await svc.upsert_production(session, principal, body))


# --------------------------------------------------------------- environment
@router.get("/environment/limits", response_model=list[EnvLimit])
async def environment_limits(principal: CurrentPrincipal) -> list[EnvLimit]:
    return [EnvLimit.model_validate(x) for x in svc.limits()]


@router.get("/environment/readings", response_model=Page[EnvReadingOut])
async def list_readings(
    session: DB, principal: CurrentPrincipal, paging: Paging, mine_id: uuid.UUID | None = None,
    parameter: EnvParameter | None = None, exceeded: bool | None = None,
) -> Page[EnvReadingOut]:
    rows, total = await svc.list_readings(session, principal, mine_id=mine_id, parameter=parameter,
                                          exceeded=exceeded, offset=paging.offset, limit=paging.size)
    return Page(items=[EnvReadingOut.model_validate(r) for r in rows], total=total, page=paging.page, size=paging.size)


@router.post("/environment/readings", response_model=EnvReadingOut, status_code=status.HTTP_201_CREATED)
async def create_reading(body: EnvReadingCreate, session: DB, principal: CurrentPrincipal) -> EnvReadingOut:
    """Record a reading; values beyond the statutory limit open an environment violation automatically."""
    return EnvReadingOut.model_validate(await svc.record_reading(session, principal, body))


@router.get("/environment/summary", response_model=EnvSummary)
async def environment_summary(session: DB, principal: CurrentPrincipal, mine_id: uuid.UUID | None = None) -> EnvSummary:
    return EnvSummary.model_validate(await svc.environment_summary(session, principal, mine_id))


@router.get("/environment/trend", response_model=list[EnvTrendPoint])
async def environment_trend(
    session: DB, principal: CurrentPrincipal, parameter: EnvParameter, mine_id: uuid.UUID | None = None,
    days: int = Query(90, ge=7, le=365),
) -> list[EnvTrendPoint]:
    return [EnvTrendPoint.model_validate(p) for p in
            await svc.environment_trend(session, principal, parameter, mine_id, days)]
