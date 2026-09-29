"""FastAPI dependencies: authentication, principal resolution, pagination."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import Depends, Query, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import security
from app.core.db import get_db
from app.core.errors import Forbidden, Unauthorized
from app.models import User
from app.models.enums import UserStatus
from app.schemas.common import PageParams
from app.services.access import Perm, Principal

_bearer = HTTPBearer(auto_error=False)

DB = Annotated[AsyncSession, Depends(get_db)]


async def get_current_user(
    request: Request,
    session: DB,
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> User:
    token = creds.credentials if creds else None
    if not token:
        raise Unauthorized("Authentication required")
    try:
        claims = security.decode_access_token(token)
    except security.TokenError as exc:
        raise Unauthorized("Invalid or expired token") from exc
    if await security.access_token_revoked(claims["sub"], int(claims["iat"])):
        raise Unauthorized("Session has been revoked; please sign in again")
    user = await session.get(User, uuid.UUID(claims["sub"]))
    if user is None or user.status != UserStatus.ACTIVE:
        raise Unauthorized("Account is not active")
    request.state.user_id = str(user.id)
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


async def get_principal(user: CurrentUser) -> Principal:
    return Principal.from_user(user)


CurrentPrincipal = Annotated[Principal, Depends(get_principal)]


def require(perm: Perm):  # noqa: ANN201 - FastAPI dependency factory
    async def _dep(principal: CurrentPrincipal) -> Principal:
        if not principal.can(perm):
            raise Forbidden(f"Your role ({principal.role.value}) cannot perform '{perm.value}'")
        return principal

    return Depends(_dep)


def page_params(
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=200)] = 20,
) -> PageParams:
    return PageParams(page=page, size=size)


Paging = Annotated[PageParams, Depends(page_params)]
