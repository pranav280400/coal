from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.models.enums import MineType
from app.schemas.common import ORMModel


class SubsidiaryOut(ORMModel):
    id: uuid.UUID
    code: str
    name: str
    headquarters: str | None


class SubsidiaryCreate(BaseModel):
    code: str = Field(..., pattern=r"^[A-Z0-9]{2,16}$")
    name: str = Field(..., min_length=2, max_length=200)
    headquarters: str | None = Field(None, max_length=200)


class MineOut(ORMModel):
    id: uuid.UUID
    subsidiary_id: uuid.UUID
    subsidiary: SubsidiaryOut
    code: str
    name: str
    mine_type: MineType
    state: str
    district: str | None
    latitude: float
    longitude: float
    boundary_geojson: dict | None
    capacity_mtpa: float | None
    workforce: int | None
    is_active: bool
    risk_score: float | None
    risk_updated_at: datetime | None


class MineCreate(BaseModel):
    subsidiary_id: uuid.UUID
    code: str = Field(..., pattern=r"^[A-Z0-9-]{2,32}$")
    name: str = Field(..., min_length=2, max_length=200)
    mine_type: MineType = MineType.OPENCAST
    state: str = Field(..., max_length=100)
    district: str | None = Field(None, max_length=100)
    latitude: float = Field(..., ge=6, le=38)
    longitude: float = Field(..., ge=68, le=98)
    boundary_geojson: dict | None = None
    capacity_mtpa: float | None = Field(None, ge=0)
    workforce: int | None = Field(None, ge=0)


class MineUpdate(BaseModel):
    name: str | None = Field(None, min_length=2, max_length=200)
    mine_type: MineType | None = None
    district: str | None = None
    latitude: float | None = Field(None, ge=6, le=38)
    longitude: float | None = Field(None, ge=68, le=98)
    boundary_geojson: dict | None = None
    capacity_mtpa: float | None = Field(None, ge=0)
    workforce: int | None = Field(None, ge=0)
    is_active: bool | None = None


class MineMapPoint(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    subsidiary_code: str
    latitude: float
    longitude: float
    status: str  # compliant | minor_issues | non_compliant
    open_violations: int
    critical_violations: int
    overdue_compliance: int
    compliance_rate: float
    risk_score: float | None
