"""Authentication, access requests, password reset and user administration."""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import security
from app.core.config import get_settings
from app.core.errors import AppError, Conflict, Forbidden, InvalidState, NotFound, Unauthorized
from app.core.redis import get_redis
from app.models import Contractor, Mine, User
from app.models.base import snapshot
from app.models.enums import Role, UserStatus
from app.schemas.auth import RegisterRequest, UserCreate, UserUpdate
from app.services.access import Perm, Principal
from app.services.events import record_event

U_FIELDS = ("username", "email", "full_name", "role", "status", "subsidiary_id", "mine_id", "contractor_id")


class WeakPassword(AppError):
    status_code = 422
    code = "weak_password"


class AccountLocked(AppError):
    status_code = 429
    code = "account_locked"


def ensure_strong(password: str, *, username: str | None = None) -> None:
    problems = security.validate_password_strength(password)
    if username and username.lower() in password.lower():
        problems.append("must not contain the username")
    if problems:
        raise WeakPassword("Password " + "; ".join(problems))


async def find_login_user(session: AsyncSession, identifier: str) -> User | None:
    ident = identifier.strip().lower()
    return (
        await session.execute(
            select(User).where(or_(func.lower(User.username) == ident, func.lower(User.email) == ident))
        )
    ).scalars().first()


async def authenticate(session: AsyncSession, identifier: str, password: str) -> User:
    if await security.is_locked_out(identifier):
        raise AccountLocked(
            f"Account temporarily locked after repeated failed logins. "
            f"Try again in {get_settings().login_lockout_minutes} minutes or reset your password."
        )
    user = await find_login_user(session, identifier)
    if not security.verify_password(password, user.password_hash if user else None) or user is None:
        await security.register_failed_login(identifier)
        raise Unauthorized("Invalid username or password")
    if user.status == UserStatus.PENDING:
        raise Forbidden("Your access request is awaiting administrator approval")
    if user.status == UserStatus.DISABLED:
        raise Forbidden("Your account has been disabled")
    await security.clear_failed_logins(identifier)
    if user.password_hash and security.needs_rehash(user.password_hash):
        user.password_hash = security.hash_password(password)
    user.last_login_at = datetime.now(UTC)
    record_event(
        session, "user.login", entity_type="user", entity_id=user.id, actor=Principal.from_user(user),
        mine_id=user.mine_id, subsidiary_id=user.subsidiary_id, data={"method": "password"},
    )
    await session.commit()
    return user


async def _check_unique(session: AsyncSession, username: str, email: str, exclude: uuid.UUID | None = None) -> None:
    stmt = select(User.id).where(
        or_(func.lower(User.username) == username.lower(), func.lower(User.email) == email.lower())
    )
    if exclude:
        stmt = stmt.where(User.id != exclude)
    if (await session.execute(stmt)).first():
        raise Conflict("A user with this username or email already exists")


async def register(session: AsyncSession, data: RegisterRequest) -> User:
    ensure_strong(data.password, username=data.username)
    await _check_unique(session, data.username, str(data.email))
    mine: Mine | None = None
    if data.mine_code:
        mine = (await session.execute(select(Mine).where(Mine.code == data.mine_code.upper()))).scalars().first()
        if mine is None:
            raise NotFound("Unknown mine code")
    user = User(
        username=data.username,
        email=str(data.email).lower(),
        full_name=data.full_name,
        phone=data.phone,
        designation=data.designation,
        password_hash=security.hash_password(data.password),
        role=data.requested_role,
        status=UserStatus.PENDING,
        mine_id=mine.id if mine else None,
        subsidiary_id=mine.subsidiary_id if mine else None,
        access_request_note=data.note,
        password_changed_at=datetime.now(UTC),
    )
    session.add(user)
    await session.flush()
    record_event(
        session, "user.access_requested", entity_type="user", entity_id=user.id, actor=None,
        mine_id=user.mine_id, subsidiary_id=user.subsidiary_id, after=snapshot(user, U_FIELDS),
    )
    await session.commit()
    return user


def _reset_key(token: str) -> str:
    return f"cmg:pwreset:{hashlib.sha256(token.encode()).hexdigest()}"


async def create_password_reset(session: AsyncSession, email: str) -> tuple[User, str] | None:
    """Returns (user, token) or None. Callers must not reveal whether the email exists."""
    user = (await session.execute(select(User).where(func.lower(User.email) == email.lower()))).scalars().first()
    if user is None or user.status == UserStatus.DISABLED or not user.password_hash and user.sso_subject:
        return None
    token = security.generate_opaque_token(32)
    await get_redis().set(_reset_key(token), str(user.id), ex=get_settings().password_reset_ttl_minutes * 60)
    return user, token


async def reset_password(session: AsyncSession, token: str, new_password: str) -> User:
    user_id = await get_redis().getdel(_reset_key(token))
    if not user_id:
        raise InvalidState("Reset link is invalid or has expired")
    user = await session.get(User, uuid.UUID(user_id))
    if user is None:
        raise InvalidState("Reset link is invalid or has expired")
    ensure_strong(new_password, username=user.username)
    user.password_hash = security.hash_password(new_password)
    user.password_changed_at = datetime.now(UTC)
    record_event(session, "user.password_reset", entity_type="user", entity_id=user.id,
                 actor=Principal.from_user(user), mine_id=user.mine_id)
    await session.commit()
    await security.revoke_all_user_sessions(str(user.id))
    await security.clear_failed_logins(user.username)
    await security.clear_failed_logins(user.email)
    return user


async def change_password(session: AsyncSession, user: User, current: str, new: str) -> None:
    if not security.verify_password(current, user.password_hash):
        raise Unauthorized("Current password is incorrect")
    if current == new:
        raise InvalidState("New password must differ from the current password")
    ensure_strong(new, username=user.username)
    user.password_hash = security.hash_password(new)
    user.password_changed_at = datetime.now(UTC)
    record_event(session, "user.password_changed", entity_type="user", entity_id=user.id,
                 actor=Principal.from_user(user), mine_id=user.mine_id)
    await session.commit()
    await security.revoke_all_user_sessions(str(user.id))


# --------------------------------------------------------------- admin
async def _validate_links(session: AsyncSession, role: Role, subsidiary_id: Any, mine_id: Any, contractor_id: Any) -> Any:
    if mine_id:
        mine = await session.get(Mine, mine_id)
        if mine is None:
            raise NotFound("Mine not found")
        subsidiary_id = mine.subsidiary_id
    if role == Role.MINE_OFFICIAL and not mine_id:
        raise InvalidState("Mine officials must be linked to a mine")
    if role == Role.CONTRACTOR:
        if not contractor_id or await session.get(Contractor, contractor_id) is None:
            raise InvalidState("Contractor users must be linked to a registered contractor")
    return subsidiary_id


async def admin_create(session: AsyncSession, principal: Principal, data: UserCreate) -> User:
    principal.require(Perm.USER_ADMIN)
    ensure_strong(data.password, username=data.username)
    await _check_unique(session, data.username, str(data.email))
    subsidiary_id = await _validate_links(session, data.role, data.subsidiary_id, data.mine_id, data.contractor_id)
    user = User(
        username=data.username,
        email=str(data.email).lower(),
        full_name=data.full_name,
        designation=data.designation,
        phone=data.phone,
        password_hash=security.hash_password(data.password),
        role=data.role,
        status=UserStatus.ACTIVE,
        subsidiary_id=subsidiary_id,
        mine_id=data.mine_id,
        contractor_id=data.contractor_id,
        password_changed_at=datetime.now(UTC),
    )
    session.add(user)
    await session.flush()
    record_event(session, "user.created", entity_type="user", entity_id=user.id, actor=principal,
                 mine_id=user.mine_id, subsidiary_id=user.subsidiary_id, after=snapshot(user, U_FIELDS))
    await session.commit()
    await session.refresh(user)
    return user


async def admin_update(session: AsyncSession, principal: Principal, user_id: uuid.UUID, data: UserUpdate) -> User:
    principal.require(Perm.USER_ADMIN)
    user = await session.get(User, user_id)
    if user is None:
        raise NotFound("User not found")
    if user.id == principal.id and (data.role not in (None, user.role) or data.status == UserStatus.DISABLED):
        raise InvalidState("You cannot change your own role or disable yourself")
    before = snapshot(user, U_FIELDS)
    changes = data.model_dump(exclude_unset=True)
    for key, value in changes.items():
        setattr(user, key, value)
    user.subsidiary_id = await _validate_links(
        session, user.role, user.subsidiary_id, user.mine_id, user.contractor_id
    )
    action = "user.approved" if before["status"] == "pending" and user.status == UserStatus.ACTIVE else "user.updated"
    record_event(session, action, entity_type="user", entity_id=user.id, actor=principal,
                 mine_id=user.mine_id, subsidiary_id=user.subsidiary_id, before=before,
                 after=snapshot(user, U_FIELDS))
    await session.commit()
    if user.status == UserStatus.DISABLED or "role" in changes:
        await security.revoke_all_user_sessions(str(user.id))
    await session.refresh(user)
    return user


async def list_users(
    session: AsyncSession,
    principal: Principal,
    *,
    role: Role | None,
    status: UserStatus | None,
    q: str | None,
    mine_id: uuid.UUID | None,
    offset: int,
    limit: int,
) -> tuple[list[User], int]:
    stmt = select(User)
    if not principal.can(Perm.USER_ADMIN):
        # Non-admins may look up colleagues (e.g. to assign actions) within their scope only.
        if principal.role == Role.MINE_OFFICIAL:
            stmt = stmt.where(or_(User.mine_id == principal.mine_id, User.role == Role.CONTRACTOR))
        elif not principal.is_global:
            stmt = stmt.where(User.subsidiary_id == principal.subsidiary_id)
        stmt = stmt.where(User.status == UserStatus.ACTIVE)
    if role:
        stmt = stmt.where(User.role == role)
    if status:
        stmt = stmt.where(User.status == status)
    if mine_id:
        stmt = stmt.where(User.mine_id == mine_id)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(User.full_name.ilike(like), User.username.ilike(like), User.email.ilike(like)))
    total = (await session.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    rows = (
        await session.execute(stmt.order_by(User.status, User.full_name).offset(offset).limit(limit))
    ).scalars().unique().all()
    return list(rows), int(total)
