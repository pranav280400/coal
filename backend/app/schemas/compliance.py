from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field

from app.models.enums import ComplianceCategory, ComplianceStatus, Frequency
from app.schemas.auth import MineBrief
from app.schemas.common import ORMModel


class RegulationOut(ORMModel):
    id: uuid.UUID
    code: str
    act: str
    section: str | None
    title: str
    category: ComplianceCategory
    text: str
    authority: str | None
    is_embedded: bool


class RegulationCreate(BaseModel):
    code: str = Field(..., min_length=2, max_length=64)
    act: str = Field(..., max_length=200)
    section: str | None = Field(None, max_length=64)
    title: str = Field(..., max_length=300)
    category: ComplianceCategory
    text: str = Field(..., min_length=10, max_length=50_000)
    authority: str | None = Field(None, max_length=120)


class OwnerBrief(ORMModel):
    id: uuid.UUID
    full_name: str


class ComplianceOut(ORMModel):
    id: uuid.UUID
    mine_id: uuid.UUID
    mine: MineBrief
    category: ComplianceCategory
    title: str
    description: str | None
    regulation_id: uuid.UUID | None
    regulation_ref: str | None
    frequency: Frequency
    due_date: date
    status: ComplianceStatus
    owner: OwnerBrief | None
    last_completed_at: datetime | None
    evidence_document_id: uuid.UUID | None
    completion_notes: str | None
    escalated: bool
    created_at: datetime
    updated_at: datetime


class ComplianceCreate(BaseModel):
    mine_id: uuid.UUID
    category: ComplianceCategory
    title: str = Field(..., min_length=3, max_length=300)
    description: str | None = Field(None, max_length=5000)
    regulation_id: uuid.UUID | None = None
    regulation_ref: str | None = Field(None, max_length=200)
    frequency: Frequency = Frequency.ONE_TIME
    due_date: date
    owner_id: uuid.UUID | None = None


class ComplianceUpdate(BaseModel):
    title: str | None = Field(None, min_length=3, max_length=300)
    description: str | None = Field(None, max_length=5000)
    regulation_ref: str | None = Field(None, max_length=200)
    frequency: Frequency | None = None
    due_date: date | None = None
    owner_id: uuid.UUID | None = None
    status: ComplianceStatus | None = None


class ComplianceComplete(BaseModel):
    notes: str = Field(..., min_length=3, max_length=5000)
    evidence_document_id: uuid.UUID | None = None


class ComplianceSummary(BaseModel):
    overview: dict[str, int]
    strict_compliance_rate: float
    total: int
    compliant: int
    in_progress: int
    due: int
    overdue: int
    violated: int
    compliance_rate: float
    by_category: dict[str, dict[str, int]]
