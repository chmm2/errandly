from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.modules.auth.dependencies import require_active_user
from app.modules.auth.models import User
from app.modules.notifications import service
from app.modules.notifications.schemas import NotificationList

router = APIRouter(prefix="/notifications", tags=["notifications"])


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
