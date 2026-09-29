"""Field operations: inspections, violations, corrective actions, attendance, media."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Identity,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.crypto import EncryptedString
from app.core.db import Base
from app.models.base import Timestamps, UUIDPk, enum_type
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
from app.models.org import Mine, User


class Inspection(UUIDPk, Timestamps, Base):
    __tablename__ = "inspections"
    __table_args__ = (Index("ix_inspections_mine_time", "mine_id", "inspected_at"),)

    number: Mapped[int] = mapped_column(BigInteger, Identity(start=1001), unique=True)
    mine_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mines.id", ondelete="CASCADE"), index=True
    )
    inspector_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    inspection_type: Mapped[InspectionType] = mapped_column(enum_type(InspectionType))
    title: Mapped[str] = mapped_column(String(300))
    notes: Mapped[str] = mapped_column(Text, default="")
    checklist: Mapped[list] = mapped_column(JSONB, default=list)
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    geo_accuracy_m: Mapped[float | None] = mapped_column(Float)
    distance_from_mine_km: Mapped[float | None] = mapped_column(Float)
    geo_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    inspected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    status: Mapped[InspectionStatus] = mapped_column(
        enum_type(InspectionStatus), default=InspectionStatus.SUBMITTED
    )
    outcome: Mapped[InspectionOutcome] = mapped_column(
        enum_type(InspectionOutcome), default=InspectionOutcome.PENDING, index=True
    )
    ai_summary: Mapped[str | None] = mapped_column(Text)
    ai_findings: Mapped[dict | None] = mapped_column(JSONB)
    risk_score: Mapped[float | None] = mapped_column(Float)
    client_event_id: Mapped[str | None] = mapped_column(String(64), unique=True)
    source: Mapped[str] = mapped_column(String(16), default="web")
    workflow_id: Mapped[str | None] = mapped_column(String(128))

    mine: Mapped[Mine] = relationship(lazy="joined")
    inspector: Mapped[User] = relationship(lazy="joined")


class MediaFile(UUIDPk, Timestamps, Base):
    """Geo-tagged photo/file evidence attached to an inspection, violation or action."""

    __tablename__ = "media_files"
    __table_args__ = (Index("ix_media_entity", "entity_type", "entity_id"),)

    entity_type: Mapped[str] = mapped_column(String(32))
    entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    storage_key: Mapped[str] = mapped_column(String(512), unique=True)
    filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    sha256: Mapped[str] = mapped_column(String(64))
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    captured_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    uploaded_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    ocr_text: Mapped[str | None] = mapped_column(Text)


class Violation(UUIDPk, Timestamps, Base):
    __tablename__ = "violations"
    __table_args__ = (
        Index("ix_violations_mine_status", "mine_id", "status"),
        Index("ix_violations_mine_category_time", "mine_id", "category", "occurred_at"),
    )

    number: Mapped[int] = mapped_column(BigInteger, Identity(start=1001), unique=True)
    mine_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mines.id", ondelete="CASCADE"), index=True
    )
    inspection_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("inspections.id", ondelete="SET NULL"), index=True
    )
    contractor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("contractors.id", ondelete="SET NULL"), index=True
    )
    kind: Mapped[ViolationKind] = mapped_column(enum_type(ViolationKind), default=ViolationKind.VIOLATION)
    category: Mapped[ComplianceCategory] = mapped_column(enum_type(ComplianceCategory), index=True)
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str] = mapped_column(Text)
    severity: Mapped[Severity] = mapped_column(enum_type(Severity), index=True)
    severity_confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    ai_suggested_severity: Mapped[Severity | None] = mapped_column(enum_type(Severity))
    ai_confidence: Mapped[float | None] = mapped_column(Float)
    ai_rationale: Mapped[str | None] = mapped_column(Text)
    ai_source: Mapped[str | None] = mapped_column(String(16))  # "llm" | "rules"
    detected_by: Mapped[DetectedBy] = mapped_column(enum_type(DetectedBy), default=DetectedBy.HUMAN)
    status: Mapped[ViolationStatus] = mapped_column(
        enum_type(ViolationStatus), default=ViolationStatus.OPEN, index=True
    )
    risk_score: Mapped[float | None] = mapped_column(Float)
    regulation_ref: Mapped[str | None] = mapped_column(String(200))
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    reported_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    confirmed_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    escalation_level: Mapped[int] = mapped_column(Integer, default=0)
    workflow_id: Mapped[str | None] = mapped_column(String(128))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    client_event_id: Mapped[str | None] = mapped_column(String(64), unique=True)

    mine: Mapped[Mine] = relationship(lazy="joined")


class CorrectiveAction(UUIDPk, Timestamps, Base):
    __tablename__ = "corrective_actions"

    violation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("violations.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str] = mapped_column(Text, default="")
    assigned_to: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    assigned_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    deadline: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    status: Mapped[ActionStatus] = mapped_column(
        enum_type(ActionStatus), default=ActionStatus.ASSIGNED, index=True
    )
    completion_notes: Mapped[str | None] = mapped_column(Text)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    verified_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    verification_notes: Mapped[str | None] = mapped_column(Text)
    reinspection_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("inspections.id", ondelete="SET NULL")
    )

    violation: Mapped[Violation] = relationship(lazy="joined")
    assignee: Mapped[User] = relationship(lazy="joined", foreign_keys=[assigned_to])


class AttendanceRecord(UUIDPk, Timestamps, Base):
    __tablename__ = "attendance_records"
    __table_args__ = (Index("ix_attendance_mine_time", "mine_id", "check_in_at"),)

    mine_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mines.id", ondelete="CASCADE"), index=True
    )
    recorded_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT")
    )
    contractor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("contractors.id", ondelete="SET NULL"), index=True
    )
    worker_name: Mapped[str] = mapped_column(String(200))
    worker_id_no: Mapped[str | None] = mapped_column(EncryptedString(512))
    shift: Mapped[Shift] = mapped_column(enum_type(Shift))
    check_in_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    check_out_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    geo_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    client_event_id: Mapped[str | None] = mapped_column(String(64), unique=True)
    source: Mapped[str] = mapped_column(String(16), default="web")
