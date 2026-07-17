import uuid
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.models import User
from app.modules.timetable import vit_slots
from app.modules.timetable.models import TimetableSlot

# Single campus for now; multi-campus reads campuses.timezone instead.
CAMPUS_TZ = ZoneInfo("Asia/Kolkata")


class TimetableError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def _campus_now() -> tuple[int, int]:
    """(day_of_week 0=Mon, minutes since midnight) in campus time."""
    now = datetime.now(UTC).astimezone(CAMPUS_TZ)
    return now.weekday(), now.hour * 60 + now.minute


async def list_slots(db: AsyncSession, user_id: uuid.UUID) -> list[TimetableSlot]:
    return list(
        await db.scalars(
            select(TimetableSlot)
            .where(TimetableSlot.user_id == user_id)
            .order_by(TimetableSlot.day_of_week, TimetableSlot.start_minute)
        )
    )


async def create_slot(db: AsyncSession, user: User, data) -> TimetableSlot:
    slot = TimetableSlot(
        user_id=user.id,
        day_of_week=data.day_of_week,
        start_minute=data.start_minute,
        end_minute=data.end_minute,
        label=data.label,
    )
    db.add(slot)
    try:
        await db.commit()
    except IntegrityError as e:
        await db.rollback()
        # The EXCLUDE constraint fired: overlapping slot for this user+day.
        raise TimetableError("This slot overlaps one you already have.", 409) from e
    await db.refresh(slot)
    return slot


async def set_vit_slots(
    db: AsyncSession, user: User, codes: list[str]
) -> tuple[list[TimetableSlot], list[str]]:
    """Replace the user's whole timetable from a set of VIT slot codes.

    Replace-all (not append) because a student submits their complete
    timetable — re-submitting simply overwrites. Returns (slots, unknown_codes).
    """
    blocks, unknown = vit_slots.resolve(codes)
    if not blocks:
        raise TimetableError(
            "No valid VIT slots recognised. Paste codes like A1, TB2, L11.", 400
        )
    await db.execute(delete(TimetableSlot).where(TimetableSlot.user_id == user.id))
    for day, start, end, label in blocks:
        db.add(
            TimetableSlot(
                user_id=user.id,
                day_of_week=day,
                start_minute=start,
                end_minute=end,
                label=label,
            )
        )
    try:
        await db.commit()
    except IntegrityError as e:
        await db.rollback()
        # Two chosen slots claim the same time — a real timetable never does.
        raise TimetableError(
            "Those slots overlap each other — double-check what you pasted.", 409
        ) from e
    return await list_slots(db, user.id), unknown


async def delete_slot(db: AsyncSession, user: User, slot_id: uuid.UUID) -> None:
    slot = await db.get(TimetableSlot, slot_id)
    if slot is None or slot.user_id != user.id:
        raise TimetableError("Slot not found.", 404)
    await db.delete(slot)
    await db.commit()


async def current_slot(db: AsyncSession, user_id: uuid.UUID) -> TimetableSlot | None:
    """The class the user is sitting in right now, if any."""
    day, minute = _campus_now()
    return await db.scalar(
        select(TimetableSlot).where(
            TimetableSlot.user_id == user_id,
            TimetableSlot.day_of_week == day,
            TimetableSlot.start_minute <= minute,
            TimetableSlot.end_minute > minute,
        )
    )


async def in_class_user_ids(db: AsyncSession, user_ids: list[uuid.UUID]) -> set[uuid.UUID]:
    """Which of these users are in class right now — used by matching to
    skip them and by the enforcer to auto-block them."""
    if not user_ids:
        return set()
    day, minute = _campus_now()
    rows = await db.scalars(
        select(TimetableSlot.user_id).where(
            TimetableSlot.user_id.in_(user_ids),
            TimetableSlot.day_of_week == day,
            TimetableSlot.start_minute <= minute,
            TimetableSlot.end_minute > minute,
        )
    )
    return set(rows)
