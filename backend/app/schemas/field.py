from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.models.enums import (
    ActionStatus,
    ComplianceCategory,
    DetectedBy,
    InspectionOutcome,
    InspectionStatus,
    InspectionType,
    Severity,
    Shift,
    ViolationKind,
    ViolationStatus,
)
from app.schemas.auth import MineBrief
from app.schemas.common import GeoPoint, ORMModel
from app.schemas.compliance import OwnerBrief


class ChecklistItem(BaseModel):
    item: str = Field(..., min_length=1, max_length=300)
    passed: bool
    note: str | None = Field(None, max_length=1000)


class MediaOut(ORMModel):
    id: uuid.UUID
    filename: str
    content_type: str
    size_bytes: int
    sha256: str
    latitude: float | None
    longitude: float | None
    captured_at: datetime | None
    created_at: datetime


# ------------------------------------------------------------ inspections
class InspectionCreate(BaseModel):
    mine_id: uuid.UUID
    inspection_type: InspectionType
    title: str = Field(..., min_length=3, max_length=300)
    notes: str = Field("", max_length=20_000)
    checklist: list[ChecklistItem] = Field(default_factory=list, max_length=200)
    geo: GeoPoint | None = None
    inspected_at: datetime | None = None
    outcome: InspectionOutcome | None = None
    client_event_id: str | None = Field(None, min_length=8, max_length=64)


class InspectionReview(BaseModel):
    outcome: InspectionOutcome
    notes: str | None = Field(None, max_length=20_000)


class InspectionOut(ORMModel):
    id: uuid.UUID
    number: int
    mine_id: uuid.UUID
    mine: MineBrief
    inspector: OwnerBrief
    inspection_type: InspectionType
    title: str
    notes: str
    checklist: list[dict]
    latitude: float | None
    longitude: float | None
    geo_accuracy_m: float | None
    distance_from_mine_km: float | None
    geo_verified: bool
    inspected_at: datetime
    status: InspectionStatus
    outcome: InspectionOutcome
    ai_summary: str | None
    ai_findings: dict | None
    risk_score: float | None
    source: str
    created_at: datetime


class InspectionDetail(InspectionOut):
    media: list[MediaOut] = []
    violations: list[ViolationOut] = []


# ------------------------------------------------------------- violations
class ViolationCreate(BaseModel):
    mine_id: uuid.UUID
    inspection_id: uuid.UUID | None = None
    contractor_id: uuid.UUID | None = None
    kind: ViolationKind = ViolationKind.VIOLATION
    category: ComplianceCategory
    title: str = Field(..., min_length=3, max_length=300)
    description: str = Field(..., min_length=5, max_length=20_000)
    severity: Severity | None = Field(
        None, description="Reporter's severity; if omitted the AI suggestion is used pending confirmation"
    )
    regulation_ref: str | None = Field(None, max_length=200)
    geo: GeoPoint | None = None
    occurred_at: datetime | None = None
    client_event_id: str | None = Field(None, min_length=8, max_length=64)


class ViolationConfirm(BaseModel):
    severity: Severity
    notes: str | None = Field(None, max_length=2000)


class ViolationClose(BaseModel):
    notes: str = Field(..., min_length=3, max_length=2000)


class ViolationOut(ORMModel):
    id: uuid.UUID
    number: int
    mine_id: uuid.UUID
    mine: MineBrief
    inspection_id: uuid.UUID | None
    contractor_id: uuid.UUID | None
    kind: ViolationKind
    category: ComplianceCategory
    title: str
    description: str
    severity: Severity
    severity_confirmed: bool
    ai_suggested_severity: Severity | None
    ai_confidence: float | None
    ai_rationale: str | None
    ai_source: str | None
    detected_by: DetectedBy
    status: ViolationStatus
    risk_score: float | None
    regulation_ref: str | None
    latitude: float | None
    longitude: float | None
    occurred_at: datetime
    escalation_level: int
    closed_at: datetime | None
    created_at: datetime


class SimilarItem(BaseModel):
    source_type: str
    source_id: str
    title: str
    snippet: str
    score: float
    mine_id: str | None = None


# ----------------------------------------------------- corrective actions
class ActionCreate(BaseModel):
    violation_id: uuid.UUID
    title: str = Field(..., min_length=3, max_length=300)
    description: str = Field("", max_length=10_000)
    assigned_to: uuid.UUID
    deadline: datetime

    @model_validator(mode="after")
    def _future(self) -> ActionCreate:
        if self.deadline.tzinfo is None:
            raise ValueError("deadline must include a timezone")
        return self


class ActionSubmit(BaseModel):
    completion_notes: str = Field(..., min_length=5, max_length=10_000)


class ActionVerify(BaseModel):
    decision: Literal["approve", "reject"]
    notes: str = Field(..., min_length=3, max_length=5000)
    reinspection_id: uuid.UUID | None = None


class ActionOut(ORMModel):
    id: uuid.UUID
    violation_id: uuid.UUID
    violation_number: int | None = None
    violation_title: str | None = None
    mine_name: str | None = None
    title: str
    description: str
    assignee: OwnerBrief
    deadline: datetime
    status: ActionStatus
    completion_notes: str | None
    submitted_at: datetime | None
    verified_at: datetime | None
    verification_notes: str | None
    reinspection_id: uuid.UUID | None
    created_at: datetime


# ------------------------------------------------------------- attendance
class AttendanceCreate(BaseModel):
    mine_id: uuid.UUID
    worker_name: str = Field(..., min_length=2, max_length=200)
    worker_id_no: str | None = Field(None, max_length=64)
    contractor_id: uuid.UUID | None = None
    shift: Shift
    check_in_at: datetime | None = None
    check_out_at: datetime | None = None
    geo: GeoPoint | None = None
    client_event_id: str | None = Field(None, min_length=8, max_length=64)


class AttendanceOut(ORMModel):
    id: uuid.UUID
    mine_id: uuid.UUID
    worker_name: str
    contractor_id: uuid.UUID | None
    shift: Shift
    check_in_at: datetime
    check_out_at: datetime | None
    latitude: float | None
    longitude: float | None
    geo_verified: bool
    source: str


# ------------------------------------------------- offline sync (ingest)
class IngestEvent(BaseModel):
    client_event_id: str = Field(..., min_length=8, max_length=64)
    event_type: Literal["inspection.submitted", "violation.reported", "attendance.logged"]
    captured_at: datetime
    payload: dict


class IngestBatch(BaseModel):
    device_id: str = Field(..., min_length=4, max_length=128)
    events: list[IngestEvent] = Field(..., min_length=1, max_length=200)


class IngestResult(BaseModel):
    client_event_id: str
    status: Literal["accepted", "duplicate", "rejected"]
    detail: str | None = None


InspectionDetail.model_rebuild()
