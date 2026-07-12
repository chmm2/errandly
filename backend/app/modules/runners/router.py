from fastapi import APIRouter, Depends, HTTPException, status
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.redis import get_redis
from app.modules.auth.dependencies import require_active_user
from app.modules.auth.models import User
from app.modules.runners import service
from app.modules.runners.schemas import AvailabilityUpdate, LocationUpdate, RunnerProfileOut
from app.modules.timetable import service as timetable

router = APIRouter(prefix="/runners", tags=["runners"])


async def _out(db: AsyncSession, profile, user_id) -> RunnerProfileOut:
    out = RunnerProfileOut.model_validate(profile)
    out.active_load = await service.active_load(db, user_id)
    return out


@router.get("/me", response_model=RunnerProfileOut)
async def my_profile(
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_db),
):
    profile = await service.get_or_create_profile(db, user)
    await db.commit()
    return await _out(db, profile, user.id)


@router.post("/me/availability", response_model=RunnerProfileOut)
async def set_availability(
    data: AvailabilityUpdate,
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
):
    # Timetable enforcement: you can't go online while you're in class.
    if data.is_available:
        slot = await timetable.current_slot(db, user.id)
        if slot is not None:
            end = f"{slot.end_minute // 60:02d}:{slot.end_minute % 60:02d}"
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                f"You have {slot.label} until {end} — runner mode unlocks after class.",
            )
    profile = await service.set_availability(db, redis, user, data)
    return await _out(db, profile, user.id)


@router.post("/me/location", response_model=RunnerProfileOut)
async def update_location(
    data: LocationUpdate,
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
):
    profile = await service.update_location(db, redis, user, data)
    return await _out(db, profile, user.id)
