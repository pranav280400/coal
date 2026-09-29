"""In-app notifications with real-time fan-out (Redis pub/sub → SSE) and channel dispatch."""

from __future__ import annotations

import json
import uuid
from collections.abc import Iterable
from datetime import UTC, datetime

from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.redis import get_redis, user_channel
from app.models import Mine, Notification, PushSubscription, User
from app.models.enums import NotificationSeverity, Role, UserStatus
from app.notifications import channels


async def recipients_for_mine(
    session: AsyncSession, mine_id: uuid.UUID | None, roles: Iterable[Role], *, include_hq: bool = False
) -> list[User]:
    """Active users of the given roles responsible for a mine (mine staff and/or its subsidiary)."""
    roles = list(roles)
    conditions = []
    if mine_id:
        mine = await session.get(Mine, mine_id)
        if mine:
            conditions.append(User.mine_id == mine_id)
            conditions.append((User.subsidiary_id == mine.subsidiary_id) & (User.role == Role.CORPORATE))
    if include_hq:
        conditions.append((User.role.in_([Role.CORPORATE, Role.ADMIN])) & (User.subsidiary_id.is_(None)))
    if not conditions:
        return []
    stmt = select(User).where(User.status == UserStatus.ACTIVE, User.role.in_(roles), or_(*conditions))
    return list((await session.execute(stmt)).scalars().unique().all())


async def notify(
    session: AsyncSession,
    users: Iterable[User],
    *,
    title: str,
    body: str,
    severity: NotificationSeverity = NotificationSeverity.INFO,
    category: str,
    link: str | None = None,
    source_event_id: str | None = None,
    email: bool | None = None,
    sms: bool = False,
) -> list[Notification]:
    """Persist notifications, publish to live streams, and dispatch external channels.

    ``email=None`` means "email if warning/critical and the user opted in".
    """
    users = list(users)
    created: list[Notification] = []
    seen: set[uuid.UUID] = set()
    for user in users:
        if user.id in seen:
            continue
        seen.add(user.id)
        n = Notification(
            user_id=user.id, title=title, body=body, severity=severity, category=category, link=link,
            source_event_id=source_event_id,
        )
        session.add(n)
        created.append(n)
    await session.flush()
    redis = get_redis()
    users_by_id = {u.id: u for u in users}
    for n in created:
        payload = {
            "id": str(n.id), "title": n.title, "body": n.body, "severity": n.severity.value,
            "category": n.category, "link": n.link, "created_at": datetime.now(UTC).isoformat(),
        }
        await redis.publish(user_channel(str(n.user_id)), json.dumps(payload))
        user = users_by_id[n.user_id]
        prefs = user.notification_prefs or {}
        want_email = email if email is not None else severity != NotificationSeverity.INFO
        if want_email and prefs.get("email", True):
            await channels.send_email(user.email, title, body, link)
        if sms and prefs.get("sms", False) and user.phone:
            await channels.send_sms(user.phone, f"Lumen: {title}. {body[:200]}")
        if prefs.get("push", True):
            await push_to_user(session, user.id, payload)
    return created


async def push_to_user(session: AsyncSession, user_id: uuid.UUID, payload: dict) -> None:
    subs = (
        await session.execute(select(PushSubscription).where(PushSubscription.user_id == user_id))
    ).scalars().all()
    for sub in subs:
        result = await channels.send_push(sub.endpoint, sub.p256dh, sub.auth, payload)
        if result == "gone":
            await session.delete(sub)


async def list_for_user(
    session: AsyncSession, user_id: uuid.UUID, *, unread_only: bool, offset: int, limit: int
) -> tuple[list[Notification], int, int]:
    stmt = select(Notification).where(Notification.user_id == user_id)
    if unread_only:
        stmt = stmt.where(Notification.read_at.is_(None))
    total = (await session.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    unread = (
        await session.execute(
            select(func.count()).where(Notification.user_id == user_id, Notification.read_at.is_(None))
        )
    ).scalar_one()
    rows = (
        await session.execute(stmt.order_by(Notification.created_at.desc()).offset(offset).limit(limit))
    ).scalars().all()
    return list(rows), int(total), int(unread)


async def mark_read(session: AsyncSession, user_id: uuid.UUID, ids: list[uuid.UUID] | None) -> int:
    stmt = update(Notification).where(Notification.user_id == user_id, Notification.read_at.is_(None))
    if ids is not None:
        stmt = stmt.where(Notification.id.in_(ids))
    result = await session.execute(stmt.values(read_at=datetime.now(UTC)))
    await session.commit()
    return int(result.rowcount or 0)


async def save_push_subscription(
    session: AsyncSession, user_id: uuid.UUID, endpoint: str, p256dh: str, auth: str, user_agent: str | None
) -> None:
    await session.execute(delete(PushSubscription).where(PushSubscription.endpoint == endpoint))
    session.add(PushSubscription(user_id=user_id, endpoint=endpoint, p256dh=p256dh, auth=auth,
                                 user_agent=(user_agent or "")[:300]))
    await session.commit()
