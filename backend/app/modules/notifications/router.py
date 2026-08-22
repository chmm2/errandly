from datetime import UTC, datetime

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field
from sqlalchemy import delete
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.modules.auth.dependencies import require_active_user
from app.modules.auth.models import User
from app.modules.notifications import service
from app.modules.notifications.models import PushToken
from app.modules.notifications.schemas import NotificationList

router = APIRouter(prefix="/notifications", tags=["notifications"])


class PushTokenIn(BaseModel):
    token: str = Field(min_length=10, max_length=255)
    platform: str | None = Field(default=None, max_length=16)


@router.get("", response_model=NotificationList)
async def my_notifications(
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_db),
):
    items, unread = await service.list_for_user(db, user.id)
    return NotificationList(items=items, unread=unread)


@router.post("/read", status_code=204)
async def mark_read(
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_db),
):
    await service.mark_all_read(db, user.id)


@router.post("/push-token", status_code=status.HTTP_204_NO_CONTENT)
async def register_push_token(
    data: PushTokenIn,
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Register this device for OS-level push.

    Upsert on the token: Expo hands the same string back for the same install,
    and re-registering on every launch is the client's normal behaviour. The
    user_id is reassigned on conflict so a shared device follows whoever logged
    in last, rather than pushing someone else's errands to them.
    """
    stmt = (
        pg_insert(PushToken)
        .values(
            token=data.token,
            user_id=user.id,
            platform=data.platform,
            last_used_at=datetime.now(UTC),
        )
        .on_conflict_do_update(
            index_elements=["token"],
            set_={
                "user_id": user.id,
                "platform": data.platform,
                "last_used_at": datetime.now(UTC),
            },
        )
    )
    await db.execute(stmt)
    await db.commit()


@router.delete("/push-token", status_code=status.HTTP_204_NO_CONTENT)
async def unregister_push_token(
    data: PushTokenIn,
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Called on logout so the next person on this device doesn't get your pushes."""
    await db.execute(
        delete(PushToken).where(PushToken.token == data.token, PushToken.user_id == user.id)
    )
    await db.commit()
