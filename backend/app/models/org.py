from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.crypto import EncryptedString
from app.core.db import Base
from app.models.base import Timestamps, UUIDPk, enum_type
from app.models.enums import MineType, Role, UserStatus


class Subsidiary(UUIDPk, Timestamps, Base):
    __tablename__ = "subsidiaries"

    code: Mapped[str] = mapped_column(String(16), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200))
    headquarters: Mapped[str | None] = mapped_column(String(200))

    mines: Mapped[list[Mine]] = relationship(back_populates="subsidiary")


class Mine(UUIDPk, Timestamps, Base):
    __tablename__ = "mines"

    subsidiary_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("subsidiaries.id", ondelete="RESTRICT"), index=True
    )
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200), index=True)
    mine_type: Mapped[MineType] = mapped_column(enum_type(MineType), default=MineType.OPENCAST)
    state: Mapped[str] = mapped_column(String(100))
    district: Mapped[str | None] = mapped_column(String(100))
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)
    # Optional GeoJSON polygon of the lease boundary for geofence checks / map overlays.
    boundary_geojson: Mapped[dict | None] = mapped_column(JSONB)
    capacity_mtpa: Mapped[float | None] = mapped_column(Float)
    workforce: Mapped[int | None] = mapped_column(Integer)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    risk_score: Mapped[float | None] = mapped_column(Float)
    risk_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    subsidiary: Mapped[Subsidiary] = relationship(back_populates="mines", lazy="joined")


class User(UUIDPk, Timestamps, Base):
    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("sso_subject", name="uq_users_sso_subject"),)

    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(200))
    designation: Mapped[str | None] = mapped_column(String(120))
    phone: Mapped[str | None] = mapped_column(EncryptedString(512))
    password_hash: Mapped[str | None] = mapped_column(String(255))
    role: Mapped[Role] = mapped_column(enum_type(Role), index=True)
    status: Mapped[UserStatus] = mapped_column(enum_type(UserStatus), default=UserStatus.PENDING, index=True)
    subsidiary_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("subsidiaries.id", ondelete="SET NULL"), index=True
    )
    mine_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mines.id", ondelete="SET NULL"), index=True
    )
    contractor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("contractors.id", ondelete="SET NULL"), index=True
    )
    preferred_language: Mapped[str] = mapped_column(String(8), default="en")
    notification_prefs: Mapped[dict] = mapped_column(
        JSONB, default=lambda: {"email": True, "sms": False, "push": True}
    )
    sso_subject: Mapped[str | None] = mapped_column(String(255))
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    password_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    access_request_note: Mapped[str | None] = mapped_column(Text)

    mine: Mapped[Mine | None] = relationship(lazy="joined", foreign_keys=[mine_id])
    subsidiary: Mapped[Subsidiary | None] = relationship(lazy="joined", foreign_keys=[subsidiary_id])

    @property
    def is_active(self) -> bool:
        return self.status == UserStatus.ACTIVE


class PushSubscription(UUIDPk, Timestamps, Base):
    __tablename__ = "push_subscriptions"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    endpoint: Mapped[str] = mapped_column(Text, unique=True)
    p256dh: Mapped[str] = mapped_column(String(255))
    auth: Mapped[str] = mapped_column(String(255))
    user_agent: Mapped[str | None] = mapped_column(String(300))
