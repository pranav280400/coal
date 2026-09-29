from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.models.enums import GrievanceCategory, GrievanceStatus, Severity
from app.schemas.auth import MineBrief
from app.schemas.common import ORMModel
from app.schemas.compliance import OwnerBrief


class GrievanceOut(ORMModel):
    id: uuid.UUID
    number: int
    mine_id: uuid.UUID
    mine: MineBrief
    category: GrievanceCategory
    subject: str
    description: str
    priority: Severity
    status: GrievanceStatus
    is_anonymous: bool
    # None when the raiser is anonymous and the viewer is not allowed to see who it was.
    raiser: OwnerBrief | None
    assignee: OwnerBrief | None
    contractor_id: uuid.UUID | None
    due_at: datetime
    escalation_level: int
    resolution_notes: str | None
    resolved_at: datetime | None
    closed_at: datetime | None
    satisfaction: int | None
    reopen_count: int
    created_at: datetime
    updated_at: datetime
    # Viewer-specific flags so the UI only offers actions the API will accept.
    is_mine: bool = False
    can_manage: bool = False


class GrievanceCreate(BaseModel):
    mine_id: uuid.UUID
    category: GrievanceCategory
    subject: str = Field(..., min_length=5, max_length=300)
    description: str = Field(..., min_length=10, max_length=5000)
    priority: Severity = Severity.MEDIUM
    is_anonymous: bool = False


class GrievanceAssign(BaseModel):
    assignee_id: uuid.UUID
    priority: Severity | None = None
    note: str | None = Field(None, max_length=2000)


class GrievanceResolve(BaseModel):
    resolution_notes: str = Field(..., min_length=10, max_length=5000)


class GrievanceReject(BaseModel):
    reason: str = Field(..., min_length=10, max_length=2000)


class GrievanceClose(BaseModel):
    satisfaction: int = Field(..., ge=1, le=5)
    comment: str | None = Field(None, max_length=2000)


class GrievanceReopen(BaseModel):
    reason: str = Field(..., min_length=10, max_length=2000)


class GrievanceSummary(BaseModel):
    total: int
    open: int
    overdue: int
    resolved: int
    closed: int
    avg_resolution_hours: float | None
    avg_satisfaction: float | None
    by_category: dict[str, int]
    by_status: dict[str, int]
