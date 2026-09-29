"""Role-based permissions and row-level tenant scoping.

Every read query on tenant data goes through :func:`scope_mines` (or the helpers
built on it) so that a mine official only ever sees their own mine, a subsidiary
corporate user only their subsidiary, and regulators/HQ everything (read-only).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from sqlalchemy import Select, false, select

from app.core.errors import Forbidden
from app.models import Mine, User
from app.models.enums import Role


class Perm(StrEnum):
    READ = "read"
    COMPLIANCE_WRITE = "compliance:write"
    INSPECTION_WRITE = "inspection:write"
    VIOLATION_WRITE = "violation:write"
    VIOLATION_CONFIRM = "violation:confirm"
    ACTION_ASSIGN = "action:assign"
    ACTION_EXECUTE = "action:execute"
    ACTION_VERIFY = "action:verify"
    CONTRACTOR_WRITE = "contractor:write"
    CONTRACTOR_VERIFY = "contractor:verify"
    ATTENDANCE_WRITE = "attendance:write"
    DOCUMENT_WRITE = "document:write"
    REPORT_GENERATE = "report:generate"
    MINE_WRITE = "mine:write"
    REGULATION_WRITE = "regulation:write"
    USER_ADMIN = "user:admin"
    AUDIT_READ = "audit:read"
    ANALYTICS_RUN = "analytics:run"
    AI_USE = "ai:use"
    GRIEVANCE_RAISE = "grievance:raise"
    GRIEVANCE_MANAGE = "grievance:manage"
    OPERATIONS_WRITE = "operations:write"


_ALL = set(Perm)

ROLE_PERMISSIONS: dict[Role, set[Perm]] = {
    Role.ADMIN: _ALL,
    Role.CORPORATE: {
        Perm.READ, Perm.COMPLIANCE_WRITE, Perm.VIOLATION_CONFIRM, Perm.ACTION_ASSIGN,
        Perm.ACTION_VERIFY, Perm.CONTRACTOR_WRITE, Perm.CONTRACTOR_VERIFY, Perm.DOCUMENT_WRITE,
        Perm.REPORT_GENERATE, Perm.AUDIT_READ, Perm.ANALYTICS_RUN, Perm.AI_USE, Perm.MINE_WRITE,
        Perm.GRIEVANCE_RAISE, Perm.GRIEVANCE_MANAGE,
    },
    Role.MINE_OFFICIAL: {
        Perm.READ, Perm.COMPLIANCE_WRITE, Perm.INSPECTION_WRITE, Perm.VIOLATION_WRITE,
        Perm.VIOLATION_CONFIRM, Perm.ACTION_ASSIGN, Perm.ACTION_EXECUTE, Perm.ACTION_VERIFY,
        Perm.CONTRACTOR_WRITE, Perm.ATTENDANCE_WRITE, Perm.DOCUMENT_WRITE, Perm.REPORT_GENERATE,
        Perm.AI_USE, Perm.GRIEVANCE_RAISE, Perm.GRIEVANCE_MANAGE, Perm.OPERATIONS_WRITE,
    },
    # Regulators: read-only, cross-subsidiary, with audit visibility.
    Role.REGULATOR: {Perm.READ, Perm.AUDIT_READ, Perm.AI_USE, Perm.REPORT_GENERATE},
    Role.CONTRACTOR: {Perm.READ, Perm.ACTION_EXECUTE, Perm.ATTENDANCE_WRITE, Perm.VIOLATION_WRITE, Perm.AI_USE,
                        Perm.GRIEVANCE_RAISE},
}


@dataclass(frozen=True, slots=True)
class Principal:
    id: uuid.UUID
    role: Role
    full_name: str
    subsidiary_id: uuid.UUID | None
    mine_id: uuid.UUID | None
    contractor_id: uuid.UUID | None

    @classmethod
    def from_user(cls, user: User) -> Principal:
        return cls(
            id=user.id,
            role=user.role,
            full_name=user.full_name,
            subsidiary_id=user.subsidiary_id,
            mine_id=user.mine_id,
            contractor_id=user.contractor_id,
        )

    def can(self, perm: Perm) -> bool:
        return perm in ROLE_PERMISSIONS.get(self.role, set())

    def require(self, perm: Perm) -> None:
        if not self.can(perm):
            raise Forbidden(f"Your role ({self.role.value}) cannot perform '{perm.value}'")

    @property
    def is_global(self) -> bool:
        """Sees every subsidiary (admin, regulators, HQ corporate users)."""
        return self.role in (Role.ADMIN, Role.REGULATOR) or (
            self.role == Role.CORPORATE and self.subsidiary_id is None
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "role": self.role.value,
            "name": self.full_name,
            "subsidiary_id": str(self.subsidiary_id) if self.subsidiary_id else None,
            "mine_id": str(self.mine_id) if self.mine_id else None,
        }


def scope_mines(stmt: Select[Any], principal: Principal, mine_col: Any) -> Select[Any]:
    """Restrict a statement to rows whose ``mine_col`` is visible to the principal."""
    if principal.is_global:
        return stmt
    if principal.role == Role.MINE_OFFICIAL:
        if principal.mine_id is None:
            return stmt.where(false())  # unassigned official sees nothing
        return stmt.where(mine_col == principal.mine_id)
    if principal.role == Role.CONTRACTOR:
        from app.models import Contract

        mine_ids = select(Contract.mine_id).where(Contract.contractor_id == principal.contractor_id)
        return stmt.where(mine_col.in_(mine_ids))
    # subsidiary-level corporate
    visible = select(Mine.id).where(Mine.subsidiary_id == principal.subsidiary_id)
    return stmt.where(mine_col.in_(visible))


async def visible_mine_ids(session: Any, principal: Principal) -> list[uuid.UUID] | None:
    """``None`` means unrestricted."""
    if principal.is_global:
        return None
    stmt = scope_mines(select(Mine.id), principal, Mine.id)
    return list((await session.execute(stmt)).scalars().all())


async def assert_mine_access(session: Any, principal: Principal, mine_id: uuid.UUID, *, write: bool = False) -> Mine:
    from app.core.errors import NotFound

    mine = await session.get(Mine, mine_id)
    if mine is None:
        raise NotFound("Mine not found")
    if principal.is_global:
        if write and principal.role == Role.REGULATOR:
            raise Forbidden("Regulators have read-only access")
        return mine
    allowed = await visible_mine_ids(session, principal)
    if allowed is not None and mine_id not in allowed:
        raise Forbidden("You do not have access to this mine")
    return mine
