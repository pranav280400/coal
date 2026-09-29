from __future__ import annotations

import uuid

from fastapi import APIRouter, Query, status
from sqlalchemy import func, or_, select

from app.api.deps import DB, CurrentPrincipal, Paging, require
from app.core.errors import Conflict, NotFound
from app.models import Mine, Regulation, Subsidiary, User
from app.models.base import snapshot
from app.models.enums import ComplianceCategory, Role, UserStatus
from app.schemas.auth import UserCreate, UserOut, UserUpdate
from app.schemas.common import Page
from app.schemas.compliance import RegulationCreate, RegulationOut
from app.schemas.org import MineCreate, MineMapPoint, MineOut, MineUpdate, SubsidiaryCreate, SubsidiaryOut
from app.services import dashboard as dashboard_svc
from app.services import users as user_svc
from app.services.access import Perm, Principal, assert_mine_access, scope_mines
from app.services.events import record_event

router = APIRouter(tags=["organisation"])

MINE_FIELDS = ("code", "name", "mine_type", "state", "district", "latitude", "longitude", "is_active")


# ------------------------------------------------------------------ users
@router.get("/users", response_model=Page[UserOut])
async def list_users(
    session: DB, principal: CurrentPrincipal, paging: Paging,
    role: Role | None = None, user_status: UserStatus | None = Query(None, alias="status"),
    q: str | None = Query(None, max_length=100), mine_id: uuid.UUID | None = None,
) -> Page[UserOut]:
    rows, total = await user_svc.list_users(
        session, principal, role=role, status=user_status, q=q, mine_id=mine_id,
        offset=paging.offset, limit=paging.size,
    )
    return Page(items=[UserOut.model_validate(u) for u in rows], total=total, page=paging.page, size=paging.size)


@router.post("/users", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def create_user(body: UserCreate, session: DB, principal: Principal = require(Perm.USER_ADMIN)) -> UserOut:
    return UserOut.model_validate(await user_svc.admin_create(session, principal, body))


@router.get("/users/{user_id}", response_model=UserOut)
async def get_user(user_id: uuid.UUID, session: DB, principal: Principal = require(Perm.USER_ADMIN)) -> UserOut:
    user = await session.get(User, user_id)
    if user is None:
        raise NotFound("User not found")
    return UserOut.model_validate(user)


@router.patch("/users/{user_id}", response_model=UserOut)
async def update_user(
    user_id: uuid.UUID, body: UserUpdate, session: DB, principal: Principal = require(Perm.USER_ADMIN)
) -> UserOut:
    return UserOut.model_validate(await user_svc.admin_update(session, principal, user_id, body))


@router.post("/users/{user_id}/approve", response_model=UserOut)
async def approve_user(user_id: uuid.UUID, session: DB, principal: Principal = require(Perm.USER_ADMIN)) -> UserOut:
    return UserOut.model_validate(
        await user_svc.admin_update(session, principal, user_id, UserUpdate(status=UserStatus.ACTIVE))
    )


# ------------------------------------------------------------ subsidiaries
@router.get("/subsidiaries", response_model=list[SubsidiaryOut])
async def list_subsidiaries(session: DB, principal: CurrentPrincipal) -> list[SubsidiaryOut]:
    stmt = select(Subsidiary).order_by(Subsidiary.code)
    if not principal.is_global:
        visible = scope_mines(select(Mine.subsidiary_id), principal, Mine.id)
        stmt = stmt.where(or_(Subsidiary.id.in_(visible), Subsidiary.id == principal.subsidiary_id))
    return [SubsidiaryOut.model_validate(s) for s in (await session.execute(stmt)).scalars().all()]


@router.post("/subsidiaries", response_model=SubsidiaryOut, status_code=status.HTTP_201_CREATED)
async def create_subsidiary(
    body: SubsidiaryCreate, session: DB, principal: Principal = require(Perm.USER_ADMIN)
) -> SubsidiaryOut:
    if (await session.execute(select(Subsidiary.id).where(Subsidiary.code == body.code))).first():
        raise Conflict("Subsidiary code already exists")
    sub = Subsidiary(**body.model_dump())
    session.add(sub)
    await session.flush()
    record_event(session, "subsidiary.created", entity_type="subsidiary", entity_id=sub.id, actor=principal,
                 subsidiary_id=sub.id, after=body.model_dump())
    await session.commit()
    return SubsidiaryOut.model_validate(sub)


# ------------------------------------------------------------------ mines
@router.get("/mines", response_model=Page[MineOut])
async def list_mines(
    session: DB, principal: CurrentPrincipal, paging: Paging,
    subsidiary_id: uuid.UUID | None = None, q: str | None = Query(None, max_length=100),
    include_inactive: bool = False,
) -> Page[MineOut]:
    stmt = scope_mines(select(Mine), principal, Mine.id)
    if not include_inactive:
        stmt = stmt.where(Mine.is_active.is_(True))
    if subsidiary_id:
        stmt = stmt.where(Mine.subsidiary_id == subsidiary_id)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(Mine.name.ilike(like), Mine.code.ilike(like), Mine.district.ilike(like)))
    total = (await session.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    rows = (await session.execute(stmt.order_by(Mine.name).offset(paging.offset).limit(paging.size))).scalars().unique().all()
    return Page(items=[MineOut.model_validate(m) for m in rows], total=total, page=paging.page, size=paging.size)


@router.get("/mines/map", response_model=list[MineMapPoint])
async def mines_map(session: DB, principal: CurrentPrincipal) -> list[MineMapPoint]:
    return [MineMapPoint.model_validate(p) for p in await dashboard_svc.mine_map_points(session, principal)]


@router.get("/mines/{mine_id}", response_model=MineOut)
async def get_mine(mine_id: uuid.UUID, session: DB, principal: CurrentPrincipal) -> MineOut:
    return MineOut.model_validate(await assert_mine_access(session, principal, mine_id))


@router.post("/mines", response_model=MineOut, status_code=status.HTTP_201_CREATED)
async def create_mine(body: MineCreate, session: DB, principal: Principal = require(Perm.MINE_WRITE)) -> MineOut:
    if not principal.is_global and principal.subsidiary_id != body.subsidiary_id:
        raise NotFound("Subsidiary not found")
    if await session.get(Subsidiary, body.subsidiary_id) is None:
        raise NotFound("Subsidiary not found")
    if (await session.execute(select(Mine.id).where(Mine.code == body.code))).first():
        raise Conflict("Mine code already exists")
    mine = Mine(**body.model_dump())
    session.add(mine)
    await session.flush()
    record_event(session, "mine.created", entity_type="mine", entity_id=mine.id, actor=principal, mine_id=mine.id,
                 subsidiary_id=mine.subsidiary_id, after=snapshot(mine, MINE_FIELDS))
    await session.commit()
    await session.refresh(mine, attribute_names=["subsidiary"])
    return MineOut.model_validate(mine)


@router.patch("/mines/{mine_id}", response_model=MineOut)
async def update_mine(
    mine_id: uuid.UUID, body: MineUpdate, session: DB, principal: Principal = require(Perm.MINE_WRITE)
) -> MineOut:
    mine = await assert_mine_access(session, principal, mine_id, write=True)
    before = snapshot(mine, MINE_FIELDS)
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(mine, k, v)
    record_event(session, "mine.updated", entity_type="mine", entity_id=mine.id, actor=principal, mine_id=mine.id,
                 subsidiary_id=mine.subsidiary_id, before=before, after=snapshot(mine, MINE_FIELDS))
    await session.commit()
    await session.refresh(mine)
    return MineOut.model_validate(mine)


# ------------------------------------------------------------ regulations
@router.get("/regulations", response_model=Page[RegulationOut])
async def list_regulations(
    session: DB, principal: CurrentPrincipal, paging: Paging,
    category: ComplianceCategory | None = None, q: str | None = Query(None, max_length=200),
) -> Page[RegulationOut]:
    stmt = select(Regulation)
    if category:
        stmt = stmt.where(Regulation.category == category)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(Regulation.title.ilike(like), Regulation.code.ilike(like), Regulation.text.ilike(like)))
    total = (await session.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    rows = (await session.execute(stmt.order_by(Regulation.act, Regulation.code).offset(paging.offset).limit(paging.size))).scalars().all()
    return Page(items=[RegulationOut.model_validate(r) for r in rows], total=total, page=paging.page, size=paging.size)


@router.post("/regulations", response_model=RegulationOut, status_code=status.HTTP_201_CREATED)
async def create_regulation(
    body: RegulationCreate, session: DB, principal: Principal = require(Perm.REGULATION_WRITE)
) -> RegulationOut:
    if (await session.execute(select(Regulation.id).where(Regulation.code == body.code))).first():
        raise Conflict("Regulation code already exists")
    reg = Regulation(**body.model_dump())
    session.add(reg)
    await session.flush()
    record_event(session, "regulation.created", entity_type="regulation", entity_id=reg.id, actor=principal,
                 after={"code": reg.code, "title": reg.title, "act": reg.act})
    await session.commit()
    return RegulationOut.model_validate(reg)
