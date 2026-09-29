from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, EmailStr, Field, model_validator

from app.models.enums import ContractorStatus, ContractStatus
from app.schemas.auth import MineBrief
from app.schemas.common import ORMModel


class ContractOut(ORMModel):
    id: uuid.UUID
    contractor_id: uuid.UUID
    mine: MineBrief
    work_order_no: str
    title: str
    value_inr: Decimal
    start_date: date
    end_date: date
    workforce_count: int
    status: ContractStatus


class ContractCreate(BaseModel):
    mine_id: uuid.UUID
    work_order_no: str = Field(..., min_length=3, max_length=64)
    title: str = Field(..., min_length=3, max_length=300)
    value_inr: Decimal = Field(..., ge=0, max_digits=16, decimal_places=2)
    start_date: date
    end_date: date
    workforce_count: int = Field(0, ge=0)

    @model_validator(mode="after")
    def _dates(self) -> ContractCreate:
        if self.end_date < self.start_date:
            raise ValueError("end_date must be on or after start_date")
        return self


class ContractorOut(ORMModel):
    id: uuid.UUID
    subsidiary_id: uuid.UUID
    name: str
    registration_no: str
    gstin: str | None
    category: str
    contact_person: str
    contact_email: str | None
    contact_phone: str | None
    address: str | None
    status: ContractorStatus
    verified: bool
    compliance_score: float
    risk_score: float | None
    active_contracts: int
    created_at: datetime


class ContractorDetail(ContractorOut):
    pan_masked: str | None = None
    contracts: list[ContractOut] = []
    open_violations: int = 0
    total_violations: int = 0


class ContractorCreate(BaseModel):
    subsidiary_id: uuid.UUID | None = None
    name: str = Field(..., min_length=2, max_length=200)
    registration_no: str = Field(..., min_length=3, max_length=64)
    gstin: str | None = Field(None, pattern=r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$")
    pan: str | None = Field(None, pattern=r"^[A-Z]{5}[0-9]{4}[A-Z]$")
    category: str = Field(..., min_length=2, max_length=80)
    contact_person: str = Field(..., min_length=2, max_length=200)
    contact_email: EmailStr | None = None
    contact_phone: str | None = Field(None, pattern=r"^\+?[0-9]{10,15}$")
    address: str | None = Field(None, max_length=500)


class ContractorUpdate(BaseModel):
    name: str | None = Field(None, min_length=2, max_length=200)
    category: str | None = Field(None, min_length=2, max_length=80)
    contact_person: str | None = Field(None, min_length=2, max_length=200)
    contact_email: EmailStr | None = None
    contact_phone: str | None = Field(None, pattern=r"^\+?[0-9]{10,15}$")
    address: str | None = Field(None, max_length=500)
    status: ContractorStatus | None = None
