import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.modules.auth.dependencies import require_active_user
from app.modules.auth.models import User
from app.modules.timetable import service
from app.modules.timetable.schemas import SlotCreate, SlotOut
from app.modules.timetable.service import TimetableError

router = APIRouter(prefix="/timetable", tags=["timetable"])


class VitSlotsRequest(BaseModel):
    # Preferred: the raw VTOP paste (grid or registered-courses list). `codes`
    # kept for callers that pre-split into clean slot codes.
    raw: str | None = Field(default=None, max_length=20000)
    codes: list[str] | None = Field(default=None, max_length=400)

    @model_validator(mode="after")
    def need_input(self):
        if not self.raw and not self.codes:
            raise ValueError("Provide `raw` (a VTOP paste) or `codes`.")
        return self


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
    """Replace the timetable from a VTOP paste, or explicit slot codes."""
    try:
        slots, unknown = await service.set_vit_slots(
            db, user, codes=data.codes, raw=data.raw
        )
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
