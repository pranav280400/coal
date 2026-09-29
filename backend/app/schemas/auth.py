from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.models.enums import Role, UserStatus
from app.schemas.common import ORMModel

USERNAME_PATTERN = r"^[a-zA-Z0-9._-]{3,64}$"


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=254)
    password: str = Field(..., min_length=1, max_length=256)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    access_expires_at: datetime
    refresh_expires_at: datetime


class RefreshRequest(BaseModel):
    refresh_token: str = Field(..., min_length=20, max_length=200)


class RegisterRequest(BaseModel):
    """Self-service access request; an administrator must approve it."""

    username: str = Field(..., pattern=USERNAME_PATTERN)
    email: EmailStr
    full_name: str = Field(..., min_length=2, max_length=200)
    password: str = Field(..., min_length=10, max_length=256)
    phone: str | None = Field(None, pattern=r"^\+?[0-9]{10,15}$")
    designation: str | None = Field(None, max_length=120)
    requested_role: Role = Role.MINE_OFFICIAL
    mine_code: str | None = Field(None, max_length=32)
    note: str | None = Field(None, max_length=1000)

    @field_validator("requested_role")
    @classmethod
    def _no_admin(cls, v: Role) -> Role:
        if v == Role.ADMIN:
            raise ValueError("admin access cannot be requested")
        return v


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str = Field(..., min_length=20, max_length=200)
    new_password: str = Field(..., min_length=10, max_length=256)


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(..., min_length=10, max_length=256)


class MineBrief(ORMModel):
    id: uuid.UUID
    code: str
    name: str


class UserOut(ORMModel):
    id: uuid.UUID
    username: str
    email: str
    full_name: str
    designation: str | None
    phone: str | None
    role: Role
    status: UserStatus
    subsidiary_id: uuid.UUID | None
    mine_id: uuid.UUID | None
    contractor_id: uuid.UUID | None
    mine: MineBrief | None = None
    preferred_language: str
    notification_prefs: dict
    last_login_at: datetime | None
    created_at: datetime
    access_request_note: str | None = None


class MeOut(UserOut):
    permissions: list[str] = []
    subsidiary_name: str | None = None


class UserCreate(BaseModel):
    username: str = Field(..., pattern=USERNAME_PATTERN)
    email: EmailStr
    full_name: str = Field(..., min_length=2, max_length=200)
    password: str = Field(..., min_length=10, max_length=256)
    role: Role
    designation: str | None = None
    phone: str | None = Field(None, pattern=r"^\+?[0-9]{10,15}$")
    subsidiary_id: uuid.UUID | None = None
    mine_id: uuid.UUID | None = None
    contractor_id: uuid.UUID | None = None


class UserUpdate(BaseModel):
    full_name: str | None = Field(None, min_length=2, max_length=200)
    designation: str | None = None
    phone: str | None = Field(None, pattern=r"^\+?[0-9]{10,15}$")
    role: Role | None = None
    status: UserStatus | None = None
    subsidiary_id: uuid.UUID | None = None
    mine_id: uuid.UUID | None = None
    contractor_id: uuid.UUID | None = None


class ProfileUpdate(BaseModel):
    full_name: str | None = Field(None, min_length=2, max_length=200)
    phone: str | None = Field(None, pattern=r"^\+?[0-9]{10,15}$")
    designation: str | None = Field(None, max_length=120)
    preferred_language: str | None = Field(None, pattern=r"^(en|hi|bn|or|te|mr|ta)$")
    notification_prefs: dict[str, bool] | None = None


class SSOConfig(BaseModel):
    enabled: bool
    provider_name: str
