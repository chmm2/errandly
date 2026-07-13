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
    ErrandItem,
    Rating,
)
from app.modules.errands.schemas import ErrandCreate
from app.modules.outbox import service as outbox
from app.modules.runners import service as runners_service
from app.modules.runners.models import RunnerProfile
from app.modules.timetable import service as timetable
from app.modules.vendors.models import MenuItem, Vendor

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


# audit event type → outbox/Kafka event type
ORDER_EVENTS = {
    "CREATED": "ORDER_CREATED",
    "ACCEPTED": "ORDER_ACCEPTED",
    "PICKED_UP": "ORDER_PICKED_UP",
    "DELIVERED": "ORDER_DELIVERED",
    "COMPLETED": "ORDER_COMPLETED",
    "CANCELLED": "ORDER_CANCELLED",
}


def _emit_order_event(db: AsyncSession, errand: Errand, event_type: str) -> None:
    """Stage the domain event in the transactional outbox — same transaction
    as the state change, so the event cannot be lost or phantom."""
    outbox.emit(
        db,
        "errand",
        errand.id,
        ORDER_EVENTS[event_type],
        {
            "errand_id": str(errand.id),
            "campus_id": str(errand.campus_id),
            "requester_id": str(errand.requester_id),
            "runner_id": str(errand.runner_id) if errand.runner_id else None,
            "status": errand.status,
            "title": errand.title,
            "category": errand.category,
            "reward": float(errand.reward),
            "collect_amount": float(errand.collect_amount or 0),
        },
    )


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


async def _offer_to_nearby_runners(db: AsyncSession, redis: Redis, errand: Errand) -> int:
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
    # Timetable enforcement at the matching seam: never offer to someone
    # sitting in class, even if the enforcer hasn't swept them out yet.
    in_class = await timetable.in_class_user_ids(db, [rid for rid, _ in nearby])
    nearby = [(rid, dist) for rid, dist in nearby if rid not in in_class]
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


async def _validate_order_items(
    db: AsyncSession, user: User, data: ErrandCreate
) -> list[ErrandItem]:
    """Order-time revalidation: the cart lives in the client, so every line
    is re-checked against the LIVE menu and repriced server-side. The client
    never sets prices — snapshots come from the database."""
    vendor = await db.get(Vendor, data.vendor_id)
    if vendor is None or vendor.campus_id != user.campus_id:
        raise ErrandError("Store not found.", 404)
    if not vendor.is_open:
        raise ErrandError(f"{vendor.name} is closed right now.", 409)

    wanted = [line.menu_item_id for line in data.items]
    menu = {
        m.id: m
        for m in await db.scalars(
            select(MenuItem).where(MenuItem.vendor_id == vendor.id, MenuItem.id.in_(wanted))
        )
    }
    problems = []
    for line in data.items:
        item = menu.get(line.menu_item_id)
        if item is None:
            problems.append("an item is no longer on the menu")
        elif not item.is_available:
            problems.append(f"{item.name} is sold out")
    if problems:
        raise ErrandError("Your cart changed: " + "; ".join(problems) + ".", 409)

    return [
        ErrandItem(
            menu_item_id=line.menu_item_id,
            name_snapshot=menu[line.menu_item_id].name,
            unit_price_snapshot=menu[line.menu_item_id].price,
            quantity=line.quantity,
        )
        for line in data.items
    ]


async def _attach_items(db: AsyncSession, errands: list[Errand]) -> None:
    """Populate .items / .items_total for serialization."""
    ids = [e.id for e in errands]
    for e in errands:
        e.items, e.items_total = [], 0.0
    if not ids:
        return
    rows = await db.scalars(select(ErrandItem).where(ErrandItem.errand_id.in_(ids)))
    by_errand: dict = {}
    for item in rows:
        by_errand.setdefault(item.errand_id, []).append(item)
    for e in errands:
        e.items = by_errand.get(e.id, [])
        e.items_total = float(
            sum(i.unit_price_snapshot * i.quantity for i in e.items)
        )


async def create_errand(db: AsyncSession, redis: Redis, user: User, data: ErrandCreate) -> Errand:
    order_items = await _validate_order_items(db, user, data) if data.items else []

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
        vendor_id=data.vendor_id if order_items else None,
    )
    db.add(errand)
    await db.flush()  # assign id before writing the event / secret / items
    for item in order_items:
        item.errand_id = errand.id
        db.add(item)
    if data.otp:
        db.add(ErrandHandoffSecret(errand_id=errand.id, otp_ciphertext=encrypt_str(data.otp)))
    _record(db, errand, user, "CREATED", {"category": data.category, "reward": data.reward})
    _emit_order_event(db, errand, "CREATED")
    await db.commit()
    await db.refresh(errand)

    offered = await _offer_to_nearby_runners(db, redis, errand)
    if offered:
        _record(db, errand, None, "OFFERED", {"runners": offered})
        await db.commit()

    errand.has_handoff_secret = data.otp is not None
    await _attach_items(db, [errand])
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
    await _attach_items(db, requested + running)
    return requested, running


async def get_errand(db: AsyncSession, user: User, errand_id: uuid.UUID) -> Errand:
    errand = await db.get(Errand, errand_id)
    if errand is None or errand.deleted_at is not None or errand.campus_id != user.campus_id:
        raise ErrandError("Errand not found.", 404)
    await _attach_secret_flags(db, [errand])
    await _attach_items(db, [errand])
    return errand


async def attach_runner_position(db: AsyncSession, user: User, errand: Errand) -> None:
    """Seed the tracking map: last known runner position, only for the two
    parties of an active run (live updates then arrive over the WebSocket)."""
    if (
        errand.runner_id is None
        or errand.status not in ("ACCEPTED", "IN_PROGRESS")
        or user.id not in (errand.requester_id, errand.runner_id)
    ):
        return
    profile = await db.get(RunnerProfile, errand.runner_id)
    if profile and profile.last_lat is not None:
        errand.runner_lat = float(profile.last_lat)
        errand.runner_lng = float(profile.last_lng)


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
        _emit_order_event(db, errand, "ACCEPTED")
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
    _emit_order_event(db, errand, event_type)
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
    _emit_order_event(db, errand, "COMPLETED")
    await db.commit()
    await db.refresh(errand)
    await publish_status(redis, errand)
    await _attach_secret_flags(db, [errand])
    return errand


async def rate_errand(
    db: AsyncSession, user: User, errand_id: uuid.UUID, stars: int, comment: str | None
) -> None:
    """Requester rates the runner after completion. Reputation is updated
    under a row lock (running average, so two ratings can't race)."""
    errand = await db.scalar(select(Errand).where(Errand.id == errand_id).with_for_update())
    if errand is None or errand.deleted_at is not None or errand.campus_id != user.campus_id:
        raise ErrandError("Errand not found.", 404)
    if errand.requester_id != user.id:
        raise ErrandError("Only the requester can rate this errand.", 403)
    if errand.status != "COMPLETED":
        raise ErrandError("You can rate once the errand is completed.", 409)
    existing = await db.get(Rating, errand_id)
    if existing is not None:
        raise ErrandError("You already rated this errand.", 409)

    db.add(
        Rating(
            errand_id=errand_id,
            rater_id=user.id,
            ratee_id=errand.runner_id,
            stars=stars,
            comment=comment,
        )
    )
    runner = await db.scalar(
        select(User).where(User.id == errand.runner_id).with_for_update()
    )
    total = float(runner.reputation_score) * runner.rating_count + stars
    runner.rating_count += 1
    runner.reputation_score = round(total / runner.rating_count, 2)
    _record(db, errand, user, "RATED", {"stars": stars})
    await db.commit()


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
    _emit_order_event(db, errand, "CANCELLED")
    await db.commit()
    await db.refresh(errand)
    await publish_status(redis, errand)
    await _attach_secret_flags(db, [errand])
    return errand
