import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.modules.auth.dependencies import require_active_user
from app.modules.auth.models import User
from app.modules.timetable import service
from app.modules.timetable.schemas import SlotCreate, SlotOut
from app.modules.timetable.service import TimetableError

router = APIRouter(prefix="/timetable", tags=["timetable"])


class VitSlotsRequest(BaseModel):
    codes: list[str] = Field(min_length=1, max_length=200)


class VitSlotsResponse(BaseModel):
    slots: list[SlotOut]
    unknown: list[str]


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


@router.put("/vit", response_model=VitSlotsResponse)
async def set_vit_slots(
    data: VitSlotsRequest,
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Replace the timetable from VIT slot codes (A1, TB2, L11 …)."""
    try:
        slots, unknown = await service.set_vit_slots(db, user, data.codes)
    except TimetableError as e:
        raise HTTPException(e.status_code, e.message) from e
    return VitSlotsResponse(slots=slots, unknown=unknown)


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
