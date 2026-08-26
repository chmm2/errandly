import json
import logging
import uuid
from datetime import UTC, datetime

from redis.asyncio import Redis
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.push import send_push
from app.modules.notifications.models import Notification, PushToken

logger = logging.getLogger(__name__)

NOTIFY_CHANNEL_PREFIX = "user:notify:"


async def create_and_push(
    db: AsyncSession,
    redis: Redis,
    user_id: uuid.UUID,
    type_: str,
    title: str,
    body: str | None = None,
    data: dict | None = None,
) -> Notification:
    """Persist the notification, then push it live to the user's WS channel.
    Called by the consumer worker; the DB row is the truth, the push is
    best-effort garnish."""
    notification = Notification(
        user_id=user_id, type=type_, title=title, body=body, data=data
    )
    db.add(notification)
    await db.flush()
    await redis.publish(
        f"{NOTIFY_CHANNEL_PREFIX}{user_id}",
        json.dumps(
            {
                "type": "notification",
                "id": str(notification.id),
                "notification_type": type_,
                "title": title,
                "body": body,
                "data": data,
            }
        ),
    )
    await _push_to_devices(db, user_id, type_, title, body, data)
    return notification


async def _push_to_devices(
    db: AsyncSession,
    user_id: uuid.UUID,
    type_: str,
    title: str,
    body: str | None,
    data: dict | None,
) -> None:
    """OS-level banner for this user's devices.

    The Redis publish above only reaches an app that's currently open; this is
    what reaches a phone in someone's pocket. Best-effort by design — the
    notification row is already written, so a push failure must not roll back
    the caller's transaction (settlement in particular).
    """
    try:
        tokens = list(
            await db.scalars(select(PushToken.token).where(PushToken.user_id == user_id))
        )
        if not tokens:
            return

        dead = await send_push(
            tokens,
            title,
            body,
            {**(data or {}), "notification_type": type_},
        )
        if dead:
            # Uninstalled apps — Expo will never deliver to these again.
            await db.execute(delete(PushToken).where(PushToken.token.in_(dead)))
            logger.info("dropped %d dead push token(s)", len(dead))
    except Exception:
        logger.exception("push delivery failed for user %s", user_id)


async def list_for_user(
    db: AsyncSession, user_id: uuid.UUID, limit: int = 30
) -> tuple[list[Notification], int]:
    items = list(
        await db.scalars(
            select(Notification)
            .where(Notification.user_id == user_id)
            .order_by(Notification.created_at.desc())
            .limit(limit)
        )
    )
    unread = (
        await db.scalar(
            select(func.count())
            .select_from(Notification)
            .where(Notification.user_id == user_id, Notification.read_at.is_(None))
        )
    ) or 0
    return items, unread


async def mark_all_read(db: AsyncSession, user_id: uuid.UUID) -> None:
    await db.execute(
        update(Notification)
        .where(Notification.user_id == user_id, Notification.read_at.is_(None))
        .values(read_at=datetime.now(UTC))
    )
    await db.commit()
