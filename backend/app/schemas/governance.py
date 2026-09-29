from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field, model_validator

from app.models.enums import (
    AnomalyKind,
    AnomalyStatus,
    DocumentType,
    NotificationSeverity,
    ProcessingStatus,
    ReportScope,
)
from app.schemas.common import ORMModel


class DocumentOut(ORMModel):
    id: uuid.UUID
    mine_id: uuid.UUID | None
    subsidiary_id: uuid.UUID | None
    title: str
    doc_type: DocumentType
    filename: str
    content_type: str
    size_bytes: int
    sha256: str
    ocr_status: ProcessingStatus
    ocr_confidence: float | None
    page_count: int | None
    extracted_fields: dict | None
    summary: str | None
    embedded_chunks: int
    error: str | None
    created_at: datetime


class DocumentDetail(DocumentOut):
    ocr_text: str | None


class NotificationOut(ORMModel):
    id: uuid.UUID
    title: str
    body: str
    severity: NotificationSeverity
    category: str
    link: str | None
    read_at: datetime | None
    created_at: datetime


class PushSubscriptionIn(BaseModel):
    endpoint: str = Field(..., min_length=10, max_length=2000)
    keys: dict[str, str]

    @model_validator(mode="after")
    def _keys(self) -> PushSubscriptionIn:
        if not {"p256dh", "auth"} <= set(self.keys):
            raise ValueError("keys must include p256dh and auth")
        if not self.endpoint.startswith("https://"):
            raise ValueError("push endpoint must be https")
        return self


class AuditOut(ORMModel):
    id: int
    event_id: uuid.UUID
    entity_type: str
    entity_id: str
    action: str
    actor_id: uuid.UUID | None
    actor_name: str | None
    mine_id: uuid.UUID | None
    before: dict | None
    after: dict | None
    ts: datetime
    prev_hash: str
    hash: str


class AuditVerifyResult(BaseModel):
    valid: bool
    checked: int
    first_invalid_id: int | None = None
    head_hash: str | None = None
    verified_at: datetime


class ReportCreate(BaseModel):
    scope: ReportScope
    scope_id: uuid.UUID | None = None
    period_start: date
    period_end: date

    @model_validator(mode="after")
    def _valid(self) -> ReportCreate:
        if self.period_end < self.period_start:
            raise ValueError("period_end must be on or after period_start")
        if (self.period_end - self.period_start).days > 400:
            raise ValueError("report period cannot exceed 400 days")
        if self.scope != ReportScope.NATIONAL and self.scope_id is None:
            raise ValueError("scope_id is required for mine/subsidiary reports")
        return self


class ReportOut(ORMModel):
    id: uuid.UUID
    title: str
    scope: ReportScope
    scope_id: uuid.UUID | None
    period_start: date
    period_end: date
    status: ProcessingStatus
    summary: str | None
    metrics: dict | None
    scheduled: bool
    error: str | None
    generated_at: datetime | None
    created_at: datetime
    has_pdf: bool = False
    has_xlsx: bool = False


class RiskEntry(BaseModel):
    entity_type: str
    entity_id: uuid.UUID
    name: str
    code: str | None = None
    score: float
    band: str
    factors: dict[str, Any]
    computed_at: datetime | None


class AnomalyOut(ORMModel):
    id: uuid.UUID
    mine_id: uuid.UUID | None
    kind: AnomalyKind
    title: str
    description: str
    metric: dict
    score: float
    status: AnomalyStatus
    detected_at: datetime


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)
    session_id: uuid.UUID | None = None
    language: str | None = Field(None, pattern=r"^(auto|en|hi|bn|or|te|mr|ta)$")
    # Files uploaded through /ai/attachments that this question is about (max 3).
    attachment_ids: list[str] = Field(default_factory=list, max_length=3)


class ChatSessionOut(ORMModel):
    id: uuid.UUID
    title: str
    language: str
    created_at: datetime
    updated_at: datetime


class ChatMessageOut(ORMModel):
    id: uuid.UUID
    role: str
    content: str
    citations: list | None
    created_at: datetime


class SemanticSearchRequest(BaseModel):
    query: str = Field(..., min_length=2, max_length=2000)
    source_types: list[str] | None = None
    limit: int = Field(10, ge=1, le=50)
