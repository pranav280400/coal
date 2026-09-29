from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator

from fastapi import APIRouter, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.api.deps import DB, CurrentUser, Paging
from app.core.config import get_settings
from app.core.redis import get_redis, user_channel
from app.models.enums import NotificationSeverity
from app.schemas.common import Message, Page
from app.schemas.governance import NotificationOut, PushSubscriptionIn
from app.services import notifications as svc

router = APIRouter(prefix="/notifications", tags=["notifications"])


class NotificationPage(Page[NotificationOut]):
    unread: int


@router.get("", response_model=NotificationPage)
async def list_notifications(user: CurrentUser, session: DB, paging: Paging, unread_only: bool = False) -> NotificationPage:
    rows, total, unread = await svc.list_for_user(session, user.id, unread_only=unread_only,
                                                  offset=paging.offset, limit=paging.size)
    return NotificationPage(items=[NotificationOut.model_validate(n) for n in rows], total=total,
                            page=paging.page, size=paging.size, unread=unread)


class MarkRead(BaseModel):
    ids: list[uuid.UUID] | None = None


@router.post("/read", response_model=Message)
async def mark_read(body: MarkRead, user: CurrentUser, session: DB) -> Message:
    n = await svc.mark_read(session, user.id, body.ids)
    return Message(detail=f"{n} notification(s) marked as read")


@router.get("/stream")
async def stream(request: Request, user: CurrentUser, session: DB) -> StreamingResponse:
    """Server-Sent Events stream of the user's notifications (fed by Redis pub/sub)."""
    # Release the pooled DB connection used for authentication; the stream only needs Redis.
    user_id = str(user.id)
    await session.close()

    async def events() -> AsyncIterator[bytes]:
        pubsub = get_redis().pubsub()
        await pubsub.subscribe(user_channel(user_id))
        try:
            yield b": connected\n\nretry: 5000\n\n"
            idle = 0.0
            while not await request.is_disconnected():
                msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if msg and msg.get("type") == "message":
                    yield f"event: notification\ndata: {msg['data']}\n\n".encode()
                    idle = 0.0
                else:
                    idle += 1.0
                    if idle >= 20:  # keep proxies from closing idle connections
                        yield b": keep-alive\n\n"
                        idle = 0.0
                await asyncio.sleep(0)
        finally:
            await pubsub.unsubscribe()
            await pubsub.aclose()

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
    )


class VapidKey(BaseModel):
    enabled: bool
    public_key: str | None


@router.get("/push/vapid-key", response_model=VapidKey)
async def vapid_key() -> VapidKey:
    s = get_settings()
    return VapidKey(enabled=bool(s.vapid_public_key and s.vapid_private_key), public_key=s.vapid_public_key)


@router.post("/push/subscribe", response_model=Message)
async def subscribe(body: PushSubscriptionIn, request: Request, user: CurrentUser, session: DB) -> Message:
    await svc.save_push_subscription(session, user.id, body.endpoint, body.keys["p256dh"], body.keys["auth"],
                                     request.headers.get("user-agent"))
    return Message(detail="Push notifications enabled on this device")


@router.post("/test", response_model=Message)
async def test_notification(user: CurrentUser, session: DB, channel: str = Query("in_app")) -> Message:
    await svc.notify(session, [user], title="Test notification",
                     body="Notifications are working on this device.",
                     severity=NotificationSeverity.INFO, category="system", link="/notifications",
                     email=channel == "email")
    await session.commit()
    return Message(detail="Test notification sent")

