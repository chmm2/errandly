import json
import uuid
from datetime import UTC, datetime

from geoalchemy2 import WKTElement
from redis.asyncio import Redis
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import decrypt_str, encrypt_str
from app.modules.auth.models import User
from app.modules.errands.models import (
    CATEGORY_FULFILLMENT,
    Errand,
    ErrandEvent,
    ErrandHandoffSecret,
)
from app.modules.errands.schemas import ErrandCreate
from app.modules.runners import service as runners_service

ACCEPT_LOCK_PREFIX = "errand:accept:"
ACCEPT_LOCK_TTL_SECONDS = 10

# Pub/sub channels: order-status pushes to watchers, offer pushes to runners.
STATUS_CHANNEL_PREFIX = "errand:status:"
OFFER_CHANNEL_PREFIX = "runner:offers:"
OFFER_RADIUS_M = 3000
OFFER_FANOUT = 5

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


async def publish_status(redis: Redis, errand: Errand) -> None:
    """Fan a status change out to anyone watching this errand's WebSocket."""
    await redis.publish(
        f"{STATUS_CHANNEL_PREFIX}{errand.id}",
        json.dumps(
            {
                "errand_id": str(errand.id),
                "status": errand.status,
                "version": errand.version,
                "runner_id": str(errand.runner_id) if errand.runner_id else None,
            }
        ),
    )


async def _offer_to_nearby_runners(redis: Redis, errand: Errand) -> int:
    """Push an offer to the nearest available runners (Redis GEO + pub/sub).

    Uses the drop point as the anchor — 'a runner already heading that way'.
    Best-effort: if Redis GEO is empty the errand still sits in the feed.
    """
    nearby = await runners_service.nearest_available_runners(
        redis,
        errand.campus_id,
        lat=float(errand.drop_lat),
        lng=float(errand.drop_lng),
        radius_m=OFFER_RADIUS_M,
        limit=OFFER_FANOUT,
        exclude=errand.requester_id,
    )
    payload = {
        "type": "offer",
        "errand_id": str(errand.id),
        "title": errand.title,
        "category": errand.category,
        "reward": float(errand.reward),
    }
    for runner_id, distance_m in nearby:
        payload["distance_m"] = round(distance_m)
        await redis.publish(f"{OFFER_CHANNEL_PREFIX}{runner_id}", json.dumps(payload))
    return len(nearby)


async def _attach_secret_flags(db: AsyncSession, errands: list[Errand]) -> None:
    """Set .has_handoff_secret on each errand (read by ErrandOut)."""
    ids = [e.id for e in errands]
    if not ids:
        return
    rows = await db.scalars(
        select(ErrandHandoffSecret.errand_id).where(ErrandHandoffSecret.errand_id.in_(ids))
    )
    with_secret = set(rows)
    for e in errands:
        e.has_handoff_secret = e.id in with_secret


async def create_errand(db: AsyncSession, redis: Redis, user: User, data: ErrandCreate) -> Errand:
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
        fulfillment_type=CATEGORY_FULFILLMENT[data.category],
        external_ref=data.external_ref,
        collect_amount=data.collect_amount,
    )
    db.add(errand)
    await db.flush()  # assign id before writing the event / secret
    if data.otp:
        db.add(ErrandHandoffSecret(errand_id=errand.id, otp_ciphertext=encrypt_str(data.otp)))
    _record(db, errand, user, "CREATED", {"category": data.category, "reward": data.reward})
    await db.commit()
    await db.refresh(errand)

    offered = await _offer_to_nearby_runners(redis, errand)
    if offered:
        _record(db, errand, None, "OFFERED", {"runners": offered})
        await db.commit()

    errand.has_handoff_secret = data.otp is not None
    return errand


async def list_feed(
    db: AsyncSession,
    user: User,
    limit: int,
    offset: int,
    lat: float | None = None,
    lng: float | None = None,
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

    if lat is not None and lng is not None:
        # Nearest-first for runners: PostGIS geography distance (meters),
        # served by the GIST index on drop_point.
        point = WKTElement(f"POINT({lng} {lat})", srid=4326)
        distance = func.ST_Distance(Errand.drop_point, point).label("distance_m")
        rows = (
            await db.execute(
                base.add_columns(distance).order_by(distance).limit(limit).offset(offset)
            )
        ).all()
        errands = []
        for errand, distance_m in rows:
            errand.distance_m = round(float(distance_m), 1)
            errands.append(errand)
    else:
        errands = list(
            await db.scalars(
                base.order_by(Errand.created_at.desc()).limit(limit).offset(offset)
            )
        )

    await _attach_secret_flags(db, errands)
    return errands, total or 0


async def list_mine(db: AsyncSession, user: User) -> tuple[list[Errand], list[Errand]]:
    requested = list(
        await db.scalars(
            select(Errand)
            .where(Errand.requester_id == user.id, Errand.deleted_at.is_(None))
            .order_by(Errand.created_at.desc())
        )
    )
    running = list(
        await db.scalars(
            select(Errand)
            .where(Errand.runner_id == user.id, Errand.deleted_at.is_(None))
            .order_by(Errand.created_at.desc())
        )
    )
    await _attach_secret_flags(db, requested + running)
    return requested, running


async def get_errand(db: AsyncSession, user: User, errand_id: uuid.UUID) -> Errand:
    errand = await db.get(Errand, errand_id)
    if errand is None or errand.deleted_at is not None or errand.campus_id != user.campus_id:
        raise ErrandError("Errand not found.", 404)
    await _attach_secret_flags(db, [errand])
    return errand


async def list_events(db: AsyncSession, user: User, errand_id: uuid.UUID) -> list[ErrandEvent]:
    await get_errand(db, user, errand_id)
    rows = await db.scalars(
        select(ErrandEvent)
        .where(ErrandEvent.errand_id == errand_id)
        .order_by(ErrandEvent.created_at)
    )
    return list(rows)


async def get_handoff_secret(
    db: AsyncSession, user: User, errand_id: uuid.UUID
) -> dict:
    """Least-privilege disclosure: assigned runner only, active run only,
    and every read lands in the audit trail."""
    errand = await get_errand(db, user, errand_id)
    if errand.runner_id != user.id:
        raise ErrandError("Only the assigned runner can view handoff details.", 403)
    if errand.status not in ("ACCEPTED", "IN_PROGRESS"):
        raise ErrandError("Handoff details are only available during an active run.", 409)

    secret = await db.get(ErrandHandoffSecret, errand_id)
    otp = decrypt_str(secret.otp_ciphertext) if secret else None

    _record(db, errand, user, "SECRET_VIEWED")
    await db.commit()
    return {
        "otp": otp,
        "external_ref": errand.external_ref,
        "collect_amount": float(errand.collect_amount),
    }


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
        # Load cap: don't let one runner hoard errands they can't deliver.
        profile = await runners_service.get_or_create_profile(db, user)
        load = await runners_service.active_load(db, user.id)
        if load >= profile.max_load:
            raise ErrandError(
                f"You already have {load} active runs. Deliver one first.", 409
            )

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
        await publish_status(redis, errand)
        await _attach_secret_flags(db, [errand])
        return errand
    finally:
        await redis.delete(lock_key)


async def _runner_step(
    db: AsyncSession,
    redis: Redis,
    user: User,
    errand_id: uuid.UUID,
    to_status: str,
    event_type: str,
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
    await publish_status(redis, errand)
    await _attach_secret_flags(db, [errand])
    return errand


async def pickup_errand(
    db: AsyncSession, redis: Redis, user: User, errand_id: uuid.UUID
) -> Errand:
    return await _runner_step(db, redis, user, errand_id, "IN_PROGRESS", "PICKED_UP")


async def deliver_errand(
    db: AsyncSession, redis: Redis, user: User, errand_id: uuid.UUID
) -> Errand:
    return await _runner_step(db, redis, user, errand_id, "DELIVERED", "DELIVERED")


async def complete_errand(
    db: AsyncSession, redis: Redis, user: User, errand_id: uuid.UUID
) -> Errand:
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
    await publish_status(redis, errand)
    await _attach_secret_flags(db, [errand])
    return errand


async def cancel_errand(
    db: AsyncSession, redis: Redis, user: User, errand_id: uuid.UUID, reason: str | None
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
    await publish_status(redis, errand)
    await _attach_secret_flags(db, [errand])
    return errand
