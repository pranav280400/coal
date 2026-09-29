"""Documents, audit trail, outbox, notifications, reports, analytics and AI chat."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Identity,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.base import Timestamps, UUIDPk, enum_type
from app.models.enums import (
    AnomalyKind,
    AnomalyStatus,
    DocumentType,
    NotificationSeverity,
    ProcessingStatus,
    ReportScope,
)


class Document(UUIDPk, Timestamps, Base):
    __tablename__ = "documents"

    mine_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mines.id", ondelete="SET NULL"), index=True
    )
    subsidiary_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("subsidiaries.id", ondelete="SET NULL"), index=True
    )
    title: Mapped[str] = mapped_column(String(300))
    doc_type: Mapped[DocumentType] = mapped_column(enum_type(DocumentType), index=True)
    storage_key: Mapped[str] = mapped_column(String(512), unique=True)
    filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    language: Mapped[str] = mapped_column(String(16), default="eng+hin")
    ocr_status: Mapped[ProcessingStatus] = mapped_column(
        enum_type(ProcessingStatus), default=ProcessingStatus.PENDING, index=True
    )
    ocr_text: Mapped[str | None] = mapped_column(Text)
    ocr_confidence: Mapped[float | None] = mapped_column(Float)
    page_count: Mapped[int | None] = mapped_column(Integer)
    extracted_fields: Mapped[dict | None] = mapped_column(JSONB)
    summary: Mapped[str | None] = mapped_column(Text)
    embedded_chunks: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text)
    uploaded_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    workflow_id: Mapped[str | None] = mapped_column(String(128))


class AuditLog(Base):
    """Append-only, hash-chained audit trail (write-once enforced by DB trigger)."""

    __tablename__ = "audit_log"
    __table_args__ = (Index("ix_audit_entity", "entity_type", "entity_id"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    event_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), unique=True)
    entity_type: Mapped[str] = mapped_column(String(48), index=True)
    entity_id: Mapped[str] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(64), index=True)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)
    actor_name: Mapped[str | None] = mapped_column(String(200))
    mine_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)
    subsidiary_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)
    before: Mapped[dict | None] = mapped_column(JSONB)
    after: Mapped[dict | None] = mapped_column(JSONB)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    prev_hash: Mapped[str] = mapped_column(String(64))
    hash: Mapped[str] = mapped_column(String(64), unique=True)


class OutboxEvent(Base):
    """Transactional outbox: domain events written atomically with state changes."""

    __tablename__ = "outbox_events"
    __table_args__ = (
        Index("ix_outbox_unpublished", "id", postgresql_where="published_at IS NULL"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    event_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), unique=True)
    topic: Mapped[str] = mapped_column(String(128))
    key: Mapped[str | None] = mapped_column(String(128))
    payload: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(Integer, default=0)


class ProcessedEvent(Base):
    """Consumer idempotency ledger (exactly-once effects on top of at-least-once delivery)."""

    __tablename__ = "processed_events"

    consumer: Mapped[str] = mapped_column(String(64), primary_key=True)
    event_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    processed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Notification(UUIDPk, Base):
    __tablename__ = "notifications"
    __table_args__ = (Index("ix_notifications_user_unread", "user_id", "read_at"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(300))
    body: Mapped[str] = mapped_column(Text)
    severity: Mapped[NotificationSeverity] = mapped_column(
        enum_type(NotificationSeverity), default=NotificationSeverity.INFO
    )
    category: Mapped[str] = mapped_column(String(48))
    link: Mapped[str | None] = mapped_column(String(300))
    source_event_id: Mapped[str | None] = mapped_column(String(64))
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )


class Report(UUIDPk, Timestamps, Base):
    __tablename__ = "reports"

    title: Mapped[str] = mapped_column(String(300))
    scope: Mapped[ReportScope] = mapped_column(enum_type(ReportScope))
    scope_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)
    period_start: Mapped[date] = mapped_column(Date)
    period_end: Mapped[date] = mapped_column(Date)
    status: Mapped[ProcessingStatus] = mapped_column(
        enum_type(ProcessingStatus), default=ProcessingStatus.PENDING
    )
    pdf_key: Mapped[str | None] = mapped_column(String(512))
    xlsx_key: Mapped[str | None] = mapped_column(String(512))
    summary: Mapped[str | None] = mapped_column(Text)
    metrics: Mapped[dict | None] = mapped_column(JSONB)
    scheduled: Mapped[bool] = mapped_column(Boolean, default=False)
    requested_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    error: Mapped[str | None] = mapped_column(Text)
    workflow_id: Mapped[str | None] = mapped_column(String(128))
    generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class RiskScore(Base):
    __tablename__ = "risk_scores"
    __table_args__ = (Index("ix_risk_entity_time", "entity_type", "entity_id", "computed_at"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    entity_type: Mapped[str] = mapped_column(String(16))  # mine | contractor
    entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    score: Mapped[float] = mapped_column(Float)
    band: Mapped[str] = mapped_column(String(16))
    factors: Mapped[dict] = mapped_column(JSONB)
    model_version: Mapped[str] = mapped_column(String(64))
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Anomaly(UUIDPk, Timestamps, Base):
    __tablename__ = "anomalies"
    __table_args__ = (Index("ix_anomaly_fingerprint_status", "fingerprint", "status"),)

    mine_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mines.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[AnomalyKind] = mapped_column(enum_type(AnomalyKind), index=True)
    fingerprint: Mapped[str] = mapped_column(String(128))
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str] = mapped_column(Text)
    metric: Mapped[dict] = mapped_column(JSONB)
    score: Mapped[float] = mapped_column(Float)
    status: Mapped[AnomalyStatus] = mapped_column(enum_type(AnomalyStatus), default=AnomalyStatus.OPEN)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    acknowledged_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )


class MLModel(UUIDPk, Timestamps, Base):
    """Registry of trained model artefacts persisted in object storage."""

    __tablename__ = "ml_models"

    name: Mapped[str] = mapped_column(String(64), index=True)
    version: Mapped[str] = mapped_column(String(64))
    storage_key: Mapped[str] = mapped_column(String(512))
    metrics: Mapped[dict] = mapped_column(JSONB)
    feature_names: Mapped[list] = mapped_column(JSONB)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    trained_samples: Mapped[int] = mapped_column(Integer)


class ChatSession(UUIDPk, Timestamps, Base):
    __tablename__ = "chat_sessions"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(200))
    language: Mapped[str] = mapped_column(String(8), default="en")


class ChatMessage(UUIDPk, Base):
    __tablename__ = "chat_messages"

    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("chat_sessions.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(String(16))
    content: Mapped[str] = mapped_column(Text)
    citations: Mapped[list | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
