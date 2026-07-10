import uuid
from datetime import UTC, datetime

from geoalchemy2 import WKTElement
from redis.asyncio import Redis
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.models import User
from app.modules.errands.models import Errand, ErrandEvent
from app.modules.errands.schemas import ErrandCreate

ACCEPT_LOCK_PREFIX = "errand:accept:"
ACCEPT_LOCK_TTL_SECONDS = 10

# (from_status, to_status) — anything not listed is an illegal transition.
ALLOWED_TRANSITIONS = {
    ("OPEN", "ACCEPTED"),
    ("ACCEPTED", "IN_PROGRESS"),
    ("IN_PROGRESS", "DELIVERED"),
    ("DELIVERED", "COMPLETED"),
    ("OPEN", "CANCELLED"),
    ("ACCEPTED", "CANCELLED"),
}


class ErrandError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def _record(db: AsyncSession, errand: Errand, actor: User | None, event_type: str,
            payload: dict | None = None) -> None:
    db.add(
        ErrandEvent(
            errand_id=errand.id,
            actor_id=actor.id if actor else None,
            event_type=event_type,
            payload=payload,
        )
    )


def _transition(errand: Errand, to_status: str) -> None:
    if (errand.status, to_status) not in ALLOWED_TRANSITIONS:
        raise ErrandError(
            f"Cannot go from {errand.status} to {to_status}.", 409
        )
    errand.status = to_status
    errand.version += 1


async def create_errand(db: AsyncSession, user: User, data: ErrandCreate) -> Errand:
    errand = Errand(
        campus_id=user.campus_id,
        requester_id=user.id,
        category=data.category,
        title=data.title,
        notes=data.notes,
        pickup_label=data.pickup_label,
        drop_point=WKTElement(f"POINT({data.drop_lng} {data.drop_lat})", srid=4326),
        drop_lat=data.drop_lat,
        drop_lng=data.drop_lng,
        drop_label=data.drop_label,
        reward=data.reward,
    )
    db.add(errand)
    await db.flush()  # assign id before writing the event
    _record(db, errand, user, "CREATED", {"category": data.category, "reward": data.reward})
    await db.commit()
    await db.refresh(errand)
    return errand


async def list_feed(
    db: AsyncSession, user: User, limit: int, offset: int
) -> tuple[list[Errand], int]:
    base = (
        select(Errand)
        .where(
            Errand.campus_id == user.campus_id,
            Errand.status == "OPEN",
            Errand.requester_id != user.id,
            Errand.deleted_at.is_(None),
        )
    )
    total = await db.scalar(select(func.count()).select_from(base.subquery()))
    rows = await db.scalars(
        base.order_by(Errand.created_at.desc()).limit(limit).offset(offset)
    )
    return list(rows), total or 0


async def list_mine(db: AsyncSession, user: User) -> tuple[list[Errand], list[Errand]]:
    requested = await db.scalars(
        select(Errand)
        .where(Errand.requester_id == user.id, Errand.deleted_at.is_(None))
        .order_by(Errand.created_at.desc())
    )
    running = await db.scalars(
        select(Errand)
        .where(Errand.runner_id == user.id, Errand.deleted_at.is_(None))
        .order_by(Errand.created_at.desc())
    )
    return list(requested), list(running)


async def get_errand(db: AsyncSession, user: User, errand_id: uuid.UUID) -> Errand:
    errand = await db.get(Errand, errand_id)
    if errand is None or errand.deleted_at is not None or errand.campus_id != user.campus_id:
        raise ErrandError("Errand not found.", 404)
    return errand


async def list_events(db: AsyncSession, user: User, errand_id: uuid.UUID) -> list[ErrandEvent]:
    await get_errand(db, user, errand_id)
    rows = await db.scalars(
        select(ErrandEvent)
        .where(ErrandEvent.errand_id == errand_id)
        .order_by(ErrandEvent.created_at)
    )
    return list(rows)


async def accept_errand(
    db: AsyncSession, redis: Redis, user: User, errand_id: uuid.UUID
) -> Errand:
    """Two-layer contention control.

    Layer 1 (Redis SET NX + TTL): fast rejection so N racing runners don't pile
    up on the row lock — all but one fail in ~1ms without touching Postgres.
    Layer 2 (SELECT ... FOR UPDATE): correctness. Even if Redis is down or the
    lock expires mid-flight, the row lock + status guard make double-accept
    impossible. Redis is an optimization; Postgres is the guarantee.
    """
    lock_key = f"{ACCEPT_LOCK_PREFIX}{errand_id}"
    got_lock = await redis.set(lock_key, str(user.id), nx=True, ex=ACCEPT_LOCK_TTL_SECONDS)
    if not got_lock:
        raise ErrandError("Someone else is accepting this errand. Try another one.", 409)

    try:
        errand = await db.scalar(
            select(Errand).where(Errand.id == errand_id).with_for_update()
        )
        if errand is None or errand.deleted_at is not None or errand.campus_id != user.campus_id:
            raise ErrandError("Errand not found.", 404)
        if errand.requester_id == user.id:
            raise ErrandError("You cannot run your own errand.", 403)

        _transition(errand, "ACCEPTED")
        errand.runner_id = user.id
        errand.accepted_at = datetime.now(UTC)
        _record(db, errand, user, "ACCEPTED")
        await db.commit()
        await db.refresh(errand)
        return errand
    finally:
        await redis.delete(lock_key)


async def _runner_step(
    db: AsyncSession, user: User, errand_id: uuid.UUID, to_status: str, event_type: str
) -> Errand:
    errand = await db.scalar(select(Errand).where(Errand.id == errand_id).with_for_update())
    if errand is None or errand.deleted_at is not None or errand.campus_id != user.campus_id:
        raise ErrandError("Errand not found.", 404)
    if errand.runner_id != user.id:
        raise ErrandError("Only the assigned runner can do this.", 403)

    _transition(errand, to_status)
    if to_status == "DELIVERED":
        errand.delivered_at = datetime.now(UTC)
    _record(db, errand, user, event_type)
    await db.commit()
    await db.refresh(errand)
    return errand


async def pickup_errand(db: AsyncSession, user: User, errand_id: uuid.UUID) -> Errand:
    return await _runner_step(db, user, errand_id, "IN_PROGRESS", "PICKED_UP")


async def deliver_errand(db: AsyncSession, user: User, errand_id: uuid.UUID) -> Errand:
    return await _runner_step(db, user, errand_id, "DELIVERED", "DELIVERED")


async def complete_errand(db: AsyncSession, user: User, errand_id: uuid.UUID) -> Errand:
    errand = await db.scalar(select(Errand).where(Errand.id == errand_id).with_for_update())
    if errand is None or errand.deleted_at is not None or errand.campus_id != user.campus_id:
        raise ErrandError("Errand not found.", 404)
    if errand.requester_id != user.id:
        raise ErrandError("Only the requester can confirm completion.", 403)

    _transition(errand, "COMPLETED")
    errand.completed_at = datetime.now(UTC)
    _record(db, errand, user, "COMPLETED")
    await db.commit()
    await db.refresh(errand)
    return errand


async def cancel_errand(
    db: AsyncSession, user: User, errand_id: uuid.UUID, reason: str | None
) -> Errand:
    errand = await db.scalar(select(Errand).where(Errand.id == errand_id).with_for_update())
    if errand is None or errand.deleted_at is not None or errand.campus_id != user.campus_id:
        raise ErrandError("Errand not found.", 404)
    if errand.requester_id != user.id:
        raise ErrandError("Only the requester can cancel.", 403)

    _transition(errand, "CANCELLED")
    errand.cancelled_at = datetime.now(UTC)
    _record(db, errand, user, "CANCELLED", {"reason": reason} if reason else None)
    await db.commit()
    await db.refresh(errand)
    return errand
