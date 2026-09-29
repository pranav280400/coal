"""Contractor registry (FR11) and geo-tagged attendance."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Select, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import Forbidden, InvalidState, NotFound
from app.models import AttendanceRecord, Contract, Contractor, Mine, Violation
from app.models.base import snapshot
from app.models.enums import ContractorStatus, Role, ViolationStatus
from app.schemas.contractor import ContractCreate, ContractorCreate, ContractorUpdate
from app.schemas.field import AttendanceCreate
from app.services import geo
from app.services.access import Perm, Principal, assert_mine_access, scope_mines
from app.services.events import record_event

C_FIELDS = ("name", "registration_no", "gstin", "category", "status", "verified", "compliance_score")


def base_query(principal: Principal) -> Select[Any]:
    stmt = select(Contractor)
    if principal.role == Role.CONTRACTOR:
        return stmt.where(Contractor.id == principal.contractor_id)
    if principal.is_global:
        return stmt
    if principal.role == Role.MINE_OFFICIAL and principal.mine_id:
        mine = select(Mine.subsidiary_id).where(Mine.id == principal.mine_id).scalar_subquery()
        return stmt.where(Contractor.subsidiary_id == mine)
    return stmt.where(Contractor.subsidiary_id == principal.subsidiary_id)


async def list_contractors(
    session: AsyncSession,
    principal: Principal,
    *,
    status: ContractorStatus | None,
    q: str | None,
    offset: int,
    limit: int,
) -> tuple[list[Contractor], int]:
    stmt = base_query(principal)
    if status:
        stmt = stmt.where(Contractor.status == status)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(Contractor.name.ilike(like), Contractor.registration_no.ilike(like)))
    total = (await session.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    rows = (
        await session.execute(stmt.order_by(Contractor.compliance_score, Contractor.name).offset(offset).limit(limit))
    ).scalars().unique().all()
    return list(rows), int(total)


async def get_contractor(session: AsyncSession, principal: Principal, contractor_id: uuid.UUID) -> Contractor:
    row = (await session.execute(base_query(principal).where(Contractor.id == contractor_id))).scalars().first()
    if row is None:
        raise NotFound("Contractor not found")
    return row


async def violation_counts(session: AsyncSession, contractor_id: uuid.UUID) -> tuple[int, int]:
    total, open_ = (
        await session.execute(
            select(
                func.count(),
                func.count().filter(Violation.status != ViolationStatus.CLOSED),
            ).where(Violation.contractor_id == contractor_id)
        )
    ).one()
    return int(open_), int(total)


async def _resolve_subsidiary(session: AsyncSession, principal: Principal, requested: uuid.UUID | None) -> uuid.UUID:
    if principal.role == Role.MINE_OFFICIAL:
        if not principal.mine_id:
            raise Forbidden("Your account is not linked to a mine")
        mine = await session.get(Mine, principal.mine_id)
        assert mine is not None
        return mine.subsidiary_id
    if principal.subsidiary_id and not principal.is_global:
        return principal.subsidiary_id
    if requested is None:
        raise InvalidState("subsidiary_id is required")
    return requested


async def create_contractor(session: AsyncSession, principal: Principal, data: ContractorCreate) -> Contractor:
    principal.require(Perm.CONTRACTOR_WRITE)
    subsidiary_id = await _resolve_subsidiary(session, principal, data.subsidiary_id)
    contractor = Contractor(
        subsidiary_id=subsidiary_id,
        name=data.name,
        registration_no=data.registration_no,
        gstin=data.gstin,
        pan=data.pan,
        category=data.category,
        contact_person=data.contact_person,
        contact_email=str(data.contact_email) if data.contact_email else None,
        contact_phone=data.contact_phone,
        address=data.address,
    )
    session.add(contractor)
    await session.flush()
    record_event(
        session, "contractor.registered", entity_type="contractor", entity_id=contractor.id, actor=principal,
        subsidiary_id=subsidiary_id, after=snapshot(contractor, C_FIELDS),
    )
    await session.commit()
    return await get_contractor(session, principal, contractor.id)


async def update_contractor(
    session: AsyncSession, principal: Principal, contractor_id: uuid.UUID, data: ContractorUpdate
) -> Contractor:
    principal.require(Perm.CONTRACTOR_WRITE)
    contractor = await get_contractor(session, principal, contractor_id)
    changes = data.model_dump(exclude_unset=True)
    if "status" in changes and not principal.can(Perm.CONTRACTOR_VERIFY):
        raise Forbidden("Only corporate/admin users can change contractor status")
    before = snapshot(contractor, C_FIELDS)
    for key, value in changes.items():
        setattr(contractor, key, str(value) if key == "contact_email" and value else value)
    record_event(
        session, "contractor.updated", entity_type="contractor", entity_id=contractor.id, actor=principal,
        subsidiary_id=contractor.subsidiary_id, before=before, after=snapshot(contractor, C_FIELDS),
    )
    await session.commit()
    return await get_contractor(session, principal, contractor.id)


async def verify_contractor(session: AsyncSession, principal: Principal, contractor_id: uuid.UUID) -> Contractor:
    principal.require(Perm.CONTRACTOR_VERIFY)
    contractor = await get_contractor(session, principal, contractor_id)
    before = snapshot(contractor, C_FIELDS)
    contractor.verified = True
    if contractor.status == ContractorStatus.PENDING_VERIFICATION:
        contractor.status = ContractorStatus.ACTIVE
    record_event(
        session, "contractor.verified", entity_type="contractor", entity_id=contractor.id, actor=principal,
        subsidiary_id=contractor.subsidiary_id, before=before, after=snapshot(contractor, C_FIELDS),
    )
    await session.commit()
    return await get_contractor(session, principal, contractor.id)


async def add_contract(
    session: AsyncSession, principal: Principal, contractor_id: uuid.UUID, data: ContractCreate
) -> Contract:
    principal.require(Perm.CONTRACTOR_WRITE)
    contractor = await get_contractor(session, principal, contractor_id)
    mine = await assert_mine_access(session, principal, data.mine_id, write=True)
    if mine.subsidiary_id != contractor.subsidiary_id:
        raise InvalidState("Contract mine must belong to the contractor's subsidiary")
    if contractor.status in (ContractorStatus.BLACKLISTED, ContractorStatus.SUSPENDED):
        raise InvalidState(f"Cannot award contracts to a {contractor.status.value} contractor")
    contract = Contract(contractor_id=contractor.id, **data.model_dump())
    session.add(contract)
    await session.flush()
    record_event(
        session, "contract.awarded", entity_type="contract", entity_id=contract.id, actor=principal,
        mine_id=mine.id, subsidiary_id=mine.subsidiary_id,
        after={"contractor_id": str(contractor.id), "work_order_no": data.work_order_no,
               "value_inr": str(data.value_inr), "start_date": data.start_date.isoformat(),
               "end_date": data.end_date.isoformat()},
    )
    await session.commit()
    await session.refresh(contract)
    return contract


# ------------------------------------------------------------- attendance
def attendance_query(principal: Principal) -> Select[Any]:
    stmt = scope_mines(select(AttendanceRecord), principal, AttendanceRecord.mine_id)
    if principal.role == Role.CONTRACTOR:
        stmt = stmt.where(AttendanceRecord.contractor_id == principal.contractor_id)
    return stmt


async def log_attendance(
    session: AsyncSession, principal: Principal, data: AttendanceCreate, *, source: str = "web", commit: bool = True
) -> tuple[AttendanceRecord, bool]:
    principal.require(Perm.ATTENDANCE_WRITE)
    if data.client_event_id:
        existing = (
            await session.execute(
                select(AttendanceRecord).where(AttendanceRecord.client_event_id == data.client_event_id)
            )
        ).scalars().first()
        if existing:
            return existing, False
    mine = await assert_mine_access(session, principal, data.mine_id, write=True)
    contractor_id = principal.contractor_id if principal.role == Role.CONTRACTOR else data.contractor_id
    lat = data.geo.latitude if data.geo else None
    lon = data.geo.longitude if data.geo else None
    verified, _distance = geo.verify_location(
        lat, lon, mine.latitude, mine.longitude, mine.boundary_geojson, get_settings().geofence_radius_km
    )
    record = AttendanceRecord(
        mine_id=mine.id,
        recorded_by=principal.id,
        contractor_id=contractor_id,
        worker_name=data.worker_name,
        worker_id_no=data.worker_id_no,
        shift=data.shift,
        check_in_at=data.check_in_at or datetime.now(UTC),
        check_out_at=data.check_out_at,
        latitude=lat,
        longitude=lon,
        geo_verified=verified,
        client_event_id=data.client_event_id,
        source=source,
    )
    session.add(record)
    await session.flush()
    record_event(
        session, "attendance.logged", entity_type="attendance", entity_id=record.id, actor=principal,
        mine_id=mine.id, subsidiary_id=mine.subsidiary_id,
        after={"worker_name": data.worker_name, "shift": data.shift.value, "geo_verified": verified,
               "check_in_at": record.check_in_at.isoformat(), "source": source},
    )
    if commit:
        await session.commit()
    return record, True


async def list_attendance(
    session: AsyncSession,
    principal: Principal,
    *,
    mine_id: uuid.UUID | None,
    date_from: datetime | None,
    date_to: datetime | None,
    offset: int,
    limit: int,
) -> tuple[list[AttendanceRecord], int]:
    stmt = attendance_query(principal)
    if mine_id:
        stmt = stmt.where(AttendanceRecord.mine_id == mine_id)
    if date_from:
        stmt = stmt.where(AttendanceRecord.check_in_at >= date_from)
    if date_to:
        stmt = stmt.where(AttendanceRecord.check_in_at <= date_to)
    total = (await session.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    rows = (
        await session.execute(stmt.order_by(AttendanceRecord.check_in_at.desc()).offset(offset).limit(limit))
    ).scalars().all()
    return list(rows), int(total)
