from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.models.base import Timestamps, UUIDPk, enum_type
from app.models.enums import ComplianceCategory, ComplianceStatus, Frequency
from app.models.org import Mine, User


class Regulation(UUIDPk, Timestamps, Base):
    """Statutory provision (e.g. Coal Mines Regulations 2017, Reg. 107)."""

    __tablename__ = "regulations"

    code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    act: Mapped[str] = mapped_column(String(200))
    section: Mapped[str | None] = mapped_column(String(64))
    title: Mapped[str] = mapped_column(String(300))
    category: Mapped[ComplianceCategory] = mapped_column(enum_type(ComplianceCategory), index=True)
    text: Mapped[str] = mapped_column(Text)
    authority: Mapped[str | None] = mapped_column(String(120))
    is_embedded: Mapped[bool] = mapped_column(Boolean, default=False)


class ComplianceItem(UUIDPk, Timestamps, Base):
    __tablename__ = "compliance_items"
    __table_args__ = (
        Index("ix_compliance_items_mine_status_due", "mine_id", "status", "due_date"),
    )

    mine_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mines.id", ondelete="CASCADE"), index=True
    )
    category: Mapped[ComplianceCategory] = mapped_column(enum_type(ComplianceCategory), index=True)
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str | None] = mapped_column(Text)
    regulation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("regulations.id", ondelete="SET NULL")
    )
    regulation_ref: Mapped[str | None] = mapped_column(String(200))
    frequency: Mapped[Frequency] = mapped_column(enum_type(Frequency), default=Frequency.ONE_TIME)
    due_date: Mapped[date] = mapped_column(Date, index=True)
    status: Mapped[ComplianceStatus] = mapped_column(
        enum_type(ComplianceStatus), default=ComplianceStatus.DUE, index=True
    )
    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    last_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_completed_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    evidence_document_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="SET NULL")
    )
    completion_notes: Mapped[str | None] = mapped_column(Text)
    escalated: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )

    mine: Mapped[Mine] = relationship(lazy="joined")
    owner: Mapped[User | None] = relationship(lazy="joined", foreign_keys=[owner_id])
    regulation: Mapped[Regulation | None] = relationship(lazy="joined")
