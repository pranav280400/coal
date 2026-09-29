from __future__ import annotations

import hashlib
import uuid

from fastapi import APIRouter, status
from pydantic import BaseModel, Field

from app.api.deps import DB, CurrentUser
from app.core import security
from app.core.config import get_settings
from app.core.errors import Unauthorized
from app.core.redis import get_redis
from app.models import Subsidiary, User
from app.models.enums import UserStatus
from app.notifications import channels
from app.schemas.auth import (
    ChangePasswordRequest,
    ForgotPasswordRequest,
    LoginRequest,
    MeOut,
    ProfileUpdate,
    RefreshRequest,
    RegisterRequest,
    ResetPasswordRequest,
    SSOConfig,
    TokenResponse,
)
from app.schemas.common import Message
from app.services import sso
from app.services import users as user_svc
from app.services.access import ROLE_PERMISSIONS

router = APIRouter(prefix="/auth", tags=["auth"])


async def _tokens(user: User, family: str | None = None) -> TokenResponse:
    pair = await security.issue_token_pair(str(user.id), user.role.value, family)
    return TokenResponse(
        access_token=pair.access_token,
        refresh_token=pair.refresh_token,
        access_expires_at=pair.access_expires_at,
        refresh_expires_at=pair.refresh_expires_at,
    )


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, session: DB) -> TokenResponse:
    user = await user_svc.authenticate(session, body.username, body.password)
    return await _tokens(user)


REFRESH_REUSE_SECONDS = 30


def _grace_key(refresh_token: str) -> str:
    return "cmg:rt:grace:" + hashlib.sha256(refresh_token.encode()).hexdigest()


@router.post("/refresh", response_model=TokenResponse)
async def refresh(body: RefreshRequest, session: DB) -> TokenResponse:
    # Reuse interval: parallel requests that raced with a rotation get the same new pair
    # instead of tripping replay detection (which revokes the whole session family).
    redis = get_redis()
    cached = await redis.get(_grace_key(body.refresh_token))
    if cached:
        return TokenResponse.model_validate_json(cached)
    try:
        user_id, family = await security.rotate_refresh_token(body.refresh_token)
    except security.TokenError as exc:
        raise Unauthorized("Session expired; please sign in again") from exc
    user = await session.get(User, uuid.UUID(user_id))
    if user is None or user.status != UserStatus.ACTIVE:
        raise Unauthorized("Account is not active")
    tokens = await _tokens(user, family)
    await redis.set(_grace_key(body.refresh_token), tokens.model_dump_json(), ex=REFRESH_REUSE_SECONDS)
    return tokens


@router.post("/logout", response_model=Message)
async def logout(body: RefreshRequest) -> Message:
    await security.revoke_refresh_token(body.refresh_token)
    return Message(detail="Signed out")


@router.post("/logout-all", response_model=Message)
async def logout_all(user: CurrentUser) -> Message:
    await security.revoke_all_user_sessions(str(user.id))
    return Message(detail="All sessions revoked")


async def _me(session: DB, user: User) -> MeOut:
    out = MeOut.model_validate(user, from_attributes=True).model_copy(
        update={"permissions": sorted(p.value for p in ROLE_PERMISSIONS[user.role])}
    )
    if user.subsidiary_id:
        sub = await session.get(Subsidiary, user.subsidiary_id)
        out.subsidiary_name = sub.name if sub else None
    return out


@router.get("/me", response_model=MeOut)
async def me(user: CurrentUser, session: DB) -> MeOut:
    return await _me(session, user)


@router.patch("/me", response_model=MeOut)
async def update_me(body: ProfileUpdate, user: CurrentUser, session: DB) -> MeOut:
    changes = body.model_dump(exclude_unset=True)
    if "notification_prefs" in changes:
        allowed = {"email", "sms", "push"}
        changes["notification_prefs"] = {
            **(user.notification_prefs or {}),
            **{k: bool(v) for k, v in changes["notification_prefs"].items() if k in allowed},
        }
    for key, value in changes.items():
        setattr(user, key, value)
    await session.commit()
    await session.refresh(user)
    return await _me(session, user)


@router.post("/register", response_model=Message, status_code=status.HTTP_202_ACCEPTED)
async def register(body: RegisterRequest, session: DB) -> Message:
    await user_svc.register(session, body)
    return Message(detail="Access request submitted. An administrator will review it shortly.")


@router.post("/forgot-password", response_model=Message, status_code=status.HTTP_202_ACCEPTED)
async def forgot_password(body: ForgotPasswordRequest, session: DB) -> Message:
    result = await user_svc.create_password_reset(session, str(body.email))
    if result:
        user, token = result
        s = get_settings()
        await channels.send_email(
            user.email,
            "Reset your Lumen password",
            f"Hello {user.full_name},\n\nA password reset was requested for your account. "
            f"The link below is valid for {s.password_reset_ttl_minutes} minutes. "
            "If you did not request this, ignore this email.",
            f"/reset-password?token={token}",
        )
    # Identical response whether or not the account exists (no user enumeration).
    return Message(detail="If the email is registered, a reset link has been sent.")


@router.post("/reset-password", response_model=Message)
async def reset_password(body: ResetPasswordRequest, session: DB) -> Message:
    await user_svc.reset_password(session, body.token, body.new_password)
    return Message(detail="Password updated. Please sign in.")


@router.post("/change-password", response_model=Message)
async def change_password(body: ChangePasswordRequest, user: CurrentUser, session: DB) -> Message:
    await user_svc.change_password(session, user, body.current_password, body.new_password)
    return Message(detail="Password changed. Other sessions have been signed out.")


@router.get("/sso/config", response_model=SSOConfig)
async def sso_config() -> SSOConfig:
    s = get_settings()
    return SSOConfig(enabled=bool(s.sso_enabled and s.sso_issuer_url and s.sso_client_id),
                     provider_name=s.sso_provider_name)


class SSOAuthorizeOut(BaseModel):
    url: str


@router.get("/sso/authorize", response_model=SSOAuthorizeOut)
async def sso_authorize(return_to: str = "/dashboard") -> SSOAuthorizeOut:
    return SSOAuthorizeOut(url=await sso.build_authorize_url(return_to))


class SSOCallbackIn(BaseModel):
    code: str = Field(..., min_length=4, max_length=4096)
    state: str = Field(..., min_length=16, max_length=256)


class SSOTokenOut(TokenResponse):
    return_to: str


@router.post("/sso/callback", response_model=SSOTokenOut)
async def sso_callback(body: SSOCallbackIn, session: DB) -> SSOTokenOut:
    user, return_to = await sso.complete_login(session, body.code, body.state)
    tokens = await _tokens(user)
    return SSOTokenOut(**tokens.model_dump(), return_to=return_to)
