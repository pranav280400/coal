"""Grievance redressal, production returns and environmental monitoring."""

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
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.models.base import Timestamps, UUIDPk, enum_type
from app.models.enums import EnvParameter, GrievanceCategory, GrievanceStatus, Severity
from app.models.org import Mine, User


class Grievance(UUIDPk, Timestamps, Base):
    """A complaint raised by a worker, contractor or official, tracked to resolution under an SLA."""

    __tablename__ = "grievances"
    __table_args__ = (Index("ix_grievances_mine_status", "mine_id", "status"),)

    number: Mapped[int] = mapped_column(BigInteger, Identity(start=5001), unique=True)
    mine_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mines.id", ondelete="CASCADE"), index=True
    )
    raised_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    contractor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("contractors.id", ondelete="SET NULL"), index=True
    )
    # The raiser's identity is hidden from everyone except administrators.
    is_anonymous: Mapped[bool] = mapped_column(Boolean, default=False)
    category: Mapped[GrievanceCategory] = mapped_column(enum_type(GrievanceCategory), index=True)
    subject: Mapped[str] = mapped_column(String(300))
    description: Mapped[str] = mapped_column(Text)
    priority: Mapped[Severity] = mapped_column(enum_type(Severity), default=Severity.MEDIUM, index=True)
    status: Mapped[GrievanceStatus] = mapped_column(
        enum_type(GrievanceStatus), default=GrievanceStatus.OPEN, index=True
    )
    assigned_to: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    escalation_level: Mapped[int] = mapped_column(Integer, default=0)
    resolution_notes: Mapped[str | None] = mapped_column(Text)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    satisfaction: Mapped[int | None] = mapped_column(Integer)
    reopen_count: Mapped[int] = mapped_column(Integer, default=0)

    mine: Mapped[Mine] = relationship(lazy="joined")
    raiser: Mapped[User | None] = relationship(lazy="joined", foreign_keys=[raised_by])
    assignee: Mapped[User | None] = relationship(lazy="joined", foreign_keys=[assigned_to])


class ProductionRecord(UUIDPk, Timestamps, Base):
    """Monthly production & despatch return for one mine."""

    __tablename__ = "production_records"
    __table_args__ = (UniqueConstraint("mine_id", "period", name="uq_production_mine_period"),)

    mine_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mines.id", ondelete="CASCADE"), index=True
    )
    period: Mapped[date] = mapped_column(Date, index=True)  # first day of the month
    target_t: Mapped[float | None] = mapped_column(Float)
    produced_t: Mapped[float] = mapped_column(Float)
    dispatched_t: Mapped[float] = mapped_column(Float)
    overburden_bcm: Mapped[float | None] = mapped_column(Float)
    closing_stock_t: Mapped[float | None] = mapped_column(Float)
    notes: Mapped[str | None] = mapped_column(Text)
    recorded_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )

    mine: Mapped[Mine] = relationship(lazy="joined")


class EnvironmentReading(UUIDPk, Timestamps, Base):
    """One monitored value (air, noise or effluent) checked against its statutory limit."""

    __tablename__ = "environment_readings"
    __table_args__ = (Index("ix_env_mine_param_time", "mine_id", "parameter", "sampled_at"),)

    mine_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mines.id", ondelete="CASCADE"), index=True
    )
    parameter: Mapped[EnvParameter] = mapped_column(enum_type(EnvParameter), index=True)
    value: Mapped[float] = mapped_column(Float)
    unit: Mapped[str] = mapped_column(String(16))
    limit_min: Mapped[float | None] = mapped_column(Float)
    limit_max: Mapped[float | None] = mapped_column(Float)
    exceeded: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    station: Mapped[str] = mapped_column(String(120))
    sampled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    source: Mapped[str] = mapped_column(String(16), default="manual")  # manual | lab | sensor
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    notes: Mapped[str | None] = mapped_column(Text)
    recorded_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    violation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("violations.id", ondelete="SET NULL")
    )

    mine: Mapped[Mine] = relationship(lazy="joined")
