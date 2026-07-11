import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.modules.auth.dependencies import require_active_user
from app.modules.auth.models import User
from app.modules.timetable import service
from app.modules.timetable.schemas import SlotCreate, SlotOut
from app.modules.timetable.service import TimetableError

router = APIRouter(prefix="/timetable", tags=["timetable"])


@router.get("", response_model=list[SlotOut])
async def my_slots(
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_db),
):
    return await service.list_slots(db, user.id)


@router.post("", response_model=SlotOut, status_code=status.HTTP_201_CREATED)
async def add_slot(
    data: SlotCreate,
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await service.create_slot(db, user, data)
    except TimetableError as e:
        raise HTTPException(e.status_code, e.message) from e


@router.delete("/{slot_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_slot(
    slot_id: uuid.UUID,
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        await service.delete_slot(db, user, slot_id)
    except TimetableError as e:
        raise HTTPException(e.status_code, e.message) from e
