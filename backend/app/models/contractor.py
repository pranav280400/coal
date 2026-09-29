from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import Boolean, Date, Float, ForeignKey, Integer, Numeric, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.crypto import EncryptedString
from app.core.db import Base
from app.models.base import Timestamps, UUIDPk, enum_type
from app.models.enums import ContractorStatus, ContractStatus
from app.models.org import Mine, Subsidiary


class Contractor(UUIDPk, Timestamps, Base):
    __tablename__ = "contractors"

    subsidiary_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("subsidiaries.id", ondelete="RESTRICT"), index=True
    )
    name: Mapped[str] = mapped_column(String(200), index=True)
    registration_no: Mapped[str] = mapped_column(String(64), unique=True)
    gstin: Mapped[str | None] = mapped_column(String(15), unique=True)
    pan: Mapped[str | None] = mapped_column(EncryptedString(512))
    category: Mapped[str] = mapped_column(String(80))
    contact_person: Mapped[str] = mapped_column(String(200))
    contact_email: Mapped[str | None] = mapped_column(EncryptedString(1024))
    contact_phone: Mapped[str | None] = mapped_column(EncryptedString(512))
    address: Mapped[str | None] = mapped_column(String(500))
    status: Mapped[ContractorStatus] = mapped_column(
        enum_type(ContractorStatus), default=ContractorStatus.PENDING_VERIFICATION, index=True
    )
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    compliance_score: Mapped[float] = mapped_column(Float, default=100.0)
    risk_score: Mapped[float | None] = mapped_column(Float)

    subsidiary: Mapped[Subsidiary] = relationship(lazy="joined")
    contracts: Mapped[list[Contract]] = relationship(back_populates="contractor", lazy="selectin")

    @property
    def active_contracts(self) -> int:
        return sum(1 for c in self.contracts if c.status == ContractStatus.ACTIVE)


class Contract(UUIDPk, Timestamps, Base):
    __tablename__ = "contracts"

    contractor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("contractors.id", ondelete="CASCADE"), index=True
    )
    mine_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mines.id", ondelete="RESTRICT"), index=True
    )
    work_order_no: Mapped[str] = mapped_column(String(64), unique=True)
    title: Mapped[str] = mapped_column(String(300))
    value_inr: Mapped[float] = mapped_column(Numeric(16, 2))
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    workforce_count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[ContractStatus] = mapped_column(enum_type(ContractStatus), default=ContractStatus.ACTIVE)

    contractor: Mapped[Contractor] = relationship(back_populates="contracts")
    mine: Mapped[Mine] = relationship(lazy="joined")
