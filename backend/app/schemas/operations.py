from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field, field_validator

from app.models.enums import EnvParameter
from app.schemas.auth import MineBrief
from app.schemas.common import GeoPoint, ORMModel


# ---------------------------------------------------------------- production
class ProductionOut(ORMModel):
    id: uuid.UUID
    mine_id: uuid.UUID
    mine: MineBrief
    period: date
    target_t: float | None
    produced_t: float
    dispatched_t: float
    overburden_bcm: float | None
    closing_stock_t: float | None
    notes: str | None
    created_at: datetime
    updated_at: datetime


class ProductionUpsert(BaseModel):
    mine_id: uuid.UUID
    period: date
    target_t: float | None = Field(None, ge=0)
    produced_t: float = Field(..., ge=0)
    dispatched_t: float = Field(..., ge=0)
    overburden_bcm: float | None = Field(None, ge=0)
    closing_stock_t: float | None = Field(None, ge=0)
    notes: str | None = Field(None, max_length=2000)

    @field_validator("period")
    @classmethod
    def _month_start(cls, v: date) -> date:
        return v.replace(day=1)


class ProductionPoint(BaseModel):
    period: date
    target_t: float
    produced_t: float
    dispatched_t: float
    overburden_bcm: float


class ProductionSummary(BaseModel):
    months: list[ProductionPoint]
    ytd_produced_t: float
    ytd_dispatched_t: float
    ytd_target_t: float
    achievement_pct: float | None
    last_month_change_pct: float | None
    shortfall_mines: list[dict]


# --------------------------------------------------------------- environment
class EnvLimit(BaseModel):
    parameter: EnvParameter
    label: str
    unit: str
    group: str
    limit_min: float | None
    limit_max: float | None
    standard: str


class EnvReadingOut(ORMModel):
    id: uuid.UUID
    mine_id: uuid.UUID
    mine: MineBrief
    parameter: EnvParameter
    value: float
    unit: str
    limit_min: float | None
    limit_max: float | None
    exceeded: bool
    station: str
    sampled_at: datetime
    source: str
    latitude: float | None
    longitude: float | None
    notes: str | None
    violation_id: uuid.UUID | None
    created_at: datetime


class EnvReadingCreate(BaseModel):
    mine_id: uuid.UUID
    parameter: EnvParameter
    value: float
    station: str = Field(..., min_length=2, max_length=120)
    sampled_at: datetime | None = None
    source: str = Field("manual", pattern=r"^(manual|lab|sensor)$")
    geo: GeoPoint | None = None
    notes: str | None = Field(None, max_length=2000)


class EnvParamStatus(BaseModel):
    parameter: EnvParameter
    label: str
    unit: str
    group: str
    limit_min: float | None
    limit_max: float | None
    latest: float | None
    latest_at: datetime | None
    average_30d: float | None
    readings_30d: int
    exceedances_30d: int


class EnvTrendPoint(BaseModel):
    day: date
    average: float
    maximum: float


class EnvSummary(BaseModel):
    parameters: list[EnvParamStatus]
    exceedances_30d: int
    readings_30d: int
    compliance_pct: float | None
    worst_mines: list[dict]
