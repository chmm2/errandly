import json
import uuid
from datetime import UTC, datetime, timedelta

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
    ("ACCEPTED", "OPEN"),  # runner backs out in the grace window → re-queued
    ("OPEN", "EXPIRED"),  # nobody accepted within the window (worker sweep)
}

# How long after accepting a runner can hand an errand back to the queue.
RELEASE_WINDOW_SECONDS = 300  # 5 minutes

# After releasing an errand, that runner is locked out of re-accepting THAT
# errand for a while. Stops one person cycling accept/release to keep an errand
# out of everyone else's reach. Scoped per (errand, runner): other runners are
# unaffected, and the errand itself goes straight back into the open feed.
#
# Redis rather than a column because the state is inherently temporary — the
# TTL is the expiry mechanism, so there's nothing to sweep up later.
RELEASE_COOLDOWN_PREFIX = "errand:released:"
RELEASE_COOLDOWN_SECONDS = 300  # 5 minutes


def _cooldown_key(errand_id: uuid.UUID, runner_id: uuid.UUID) -> str:
    return f"{RELEASE_COOLDOWN_PREFIX}{errand_id}:{runner_id}"


async def _cooldown_remaining(redis: Redis, errand_id: uuid.UUID, runner_id: uuid.UUID) -> int:
    """Seconds left before this runner may retake this errand. 0 if free."""
    try:
        ttl = await redis.ttl(_cooldown_key(errand_id, runner_id))
    except Exception:
        return 0  # fail open: Redis being down shouldn't block accepting work
    return ttl if ttl and ttl > 0 else 0


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


async def _offer_to_nearby_runners(
    db: AsyncSession,
    redis: Redis,
    errand: Errand,
    exclude_runner: uuid.UUID | None = None,
) -> int:
    """Push an offer to the nearest available runners (Redis GEO + pub/sub).

    Uses the drop point as the anchor — 'a runner already heading that way'.
    Best-effort: if Redis GEO is empty the errand still sits in the feed.

    `exclude_runner` skips someone who just handed this errand back: they've
    said they don't want it, so re-offering would be noise. It still appears in
    their nearby list, so they can change their mind once the cooldown lapses.
    """
    nearby = await runners_service.nearest_available_runners(
        redis,
        errand.campus_id,
        lat=float(errand.drop_lat),
        lng=float(errand.drop_lng),
        radius_m=OFFER_RADIUS_M,
        limit=OFFER_FANOUT + (1 if exclude_runner else 0),
        exclude=errand.requester_id,
    )
    if exclude_runner:
        nearby = [(rid, dist) for rid, dist in nearby if rid != exclude_runner][:OFFER_FANOUT]
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


async def _attach_rated(db: AsyncSession, errands: list[Errand]) -> None:
    """Set .rated so the UI knows whether to offer 'rate your runner'."""
    ids = [e.id for e in errands]
    if not ids:
        return
    rows = await db.scalars(select(Rating.errand_id).where(Rating.errand_id.in_(ids)))
    rated = set(rows)
    for e in errands:
        e.rated = e.id in rated


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
        # Total counts only what's actually available and priced (unavailable
        # items drop out, shopping-list lines have no price).
        e.items_total = float(
            sum(
                (i.unit_price_snapshot or 0) * i.quantity
                for i in e.items
                if i.is_available
            )
        )


async def create_errand(db: AsyncSession, redis: Redis, user: User, data: ErrandCreate) -> Errand:
    # You can't order while you're mid-delivery for someone else. The web
    # client enforces this by locking the Order/Run toggle; enforce it here so
    # every client gets the same rule.
    running = await runners_service.active_load(db, user.id)
    if running:
        raise ErrandError(
            "Finish the run you're on before posting your own errand.", 409
        )

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
        expires_at=datetime.now(UTC) + timedelta(minutes=data.wait_minutes),
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
    # Hand-typed shopping-list lines: structured (so the runner can mark one
    # out of stock), but priceless — the runner pays the real shelf price.
    for li in data.list_items:
        db.add(
            ErrandItem(
                errand_id=errand.id,
                menu_item_id=None,
                name_snapshot=li.name.strip()[:120],
                unit_price_snapshot=None,
                quantity=li.quantity,
                note=(li.note.strip()[:200] if li.note and li.note.strip() else None),
            )
        )
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
    await _attach_rated(db, requested + running)
    return requested, running


async def get_errand(db: AsyncSession, user: User, errand_id: uuid.UUID) -> Errand:
    errand = await db.get(Errand, errand_id)
    if errand is None or errand.deleted_at is not None or errand.campus_id != user.campus_id:
        raise ErrandError("Errand not found.", 404)
    await _attach_secret_flags(db, [errand])
    await _attach_items(db, [errand])
    await _attach_rated(db, [errand])
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


async def attach_runner_summary(db: AsyncSession, user: User, errand: Errand) -> None:
    """Show the requester who's running it — name, rating, and (only during
    an active run) a phone number to call. Parties only; phone is withheld
    once the errand is finished."""
    if errand.runner_id is None or user.id not in (errand.requester_id, errand.runner_id):
        return
    runner = await db.get(User, errand.runner_id)
    if runner is None:
        return
    active = errand.status in ("ACCEPTED", "IN_PROGRESS", "DELIVERED")
    trips = await db.scalar(
        select(func.count())
        .select_from(Errand)
        .where(Errand.runner_id == runner.id, Errand.status == "COMPLETED")
    )
    errand.runner = {
        "id": runner.id,
        "display_name": runner.display_name,
        "reputation_score": float(runner.reputation_score),
        "rating_count": runner.rating_count,
        "trips_completed": trips or 0,
        "photo_url": runner.photo_url,
        "phone": runner.phone if active else None,
    }


def expire_errand(db: AsyncSession, errand: Errand) -> None:
    """OPEN → EXPIRED: nobody accepted within the window. Internal only —
    no Kafka/ledger involvement (no money or downstream fan-out for a
    non-event). Caller commits and publishes the status."""
    _transition(errand, "EXPIRED")
    _record(db, errand, None, "EXPIRED")


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
        # Cooldown: you handed this one back recently, so it's someone else's
        # turn for a few minutes.
        cooling = await _cooldown_remaining(redis, errand_id, user.id)
        if cooling:
            mins = max(1, round(cooling / 60))
            raise ErrandError(
                f"You handed this errand back — you can take it again in {mins} min.", 409
            )

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


async def release_errand(
    db: AsyncSession, redis: Redis, user: User, errand_id: uuid.UUID
) -> Errand:
    """Runner hands an accepted errand back to the queue within the grace
    window (Uber-style) — it returns to OPEN and is re-offered, not cancelled."""
    errand = await db.scalar(select(Errand).where(Errand.id == errand_id).with_for_update())
    if errand is None or errand.deleted_at is not None or errand.campus_id != user.campus_id:
        raise ErrandError("Errand not found.", 404)
    if errand.runner_id != user.id:
        raise ErrandError("Only the assigned runner can release this errand.", 403)
    if errand.status != "ACCEPTED":
        raise ErrandError("You can only release it before pickup.", 409)
    if errand.accepted_at is not None:
        elapsed = (datetime.now(UTC) - errand.accepted_at).total_seconds()
        if elapsed > RELEASE_WINDOW_SECONDS:
            raise ErrandError(
                "The 5-minute release window has passed — deliver it or cancel.", 409
            )

    _transition(errand, "OPEN")
    errand.runner_id = None
    errand.accepted_at = None
    _record(db, errand, user, "RELEASED")
    await db.commit()
    await db.refresh(errand)
    await publish_status(redis, errand)

    # Lock this runner out of retaking it for a while, so accept/release can't
    # be cycled to sit on an errand nobody else can reach.
    try:
        await redis.set(
            _cooldown_key(errand.id, user.id), "1", ex=RELEASE_COOLDOWN_SECONDS
        )
    except Exception:
        pass  # best-effort; the accept path fails open if Redis is unavailable

    # Straight back into matching — but not to the runner who just dropped it.
    offered = await _offer_to_nearby_runners(db, redis, errand, exclude_runner=user.id)
    if offered:
        _record(db, errand, None, "OFFERED", {"runners": offered})
        await db.commit()

    await _attach_secret_flags(db, [errand])
    await _attach_items(db, [errand])
    return errand


async def set_item_availability(
    db: AsyncSession,
    redis: Redis,
    user: User,
    errand_id: uuid.UUID,
    item_id: uuid.UUID,
    available: bool,
) -> Errand:
    """Runner flips one order line in/out of stock during an active run. The
    requester sees it live; an unavailable item drops out of the total."""
    errand = await db.scalar(select(Errand).where(Errand.id == errand_id).with_for_update())
    if errand is None or errand.deleted_at is not None or errand.campus_id != user.campus_id:
        raise ErrandError("Errand not found.", 404)
    if errand.runner_id != user.id:
        raise ErrandError("Only the assigned runner can update items.", 403)
    if errand.status not in ("ACCEPTED", "IN_PROGRESS"):
        raise ErrandError("Items can only be updated during an active run.", 409)

    item = await db.get(ErrandItem, item_id)
    if item is None or item.errand_id != errand.id:
        raise ErrandError("Item not found on this errand.", 404)

    item.is_available = available
    _record(
        db, errand, user,
        "ITEM_UNAVAILABLE" if not available else "ITEM_RESTORED",
        {"item": item.name_snapshot, "quantity": item.quantity},
    )
    await db.commit()
    await db.refresh(errand)
    await publish_status(redis, errand)  # nudge the requester's tracker to refetch
    await _attach_secret_flags(db, [errand])
    await _attach_items(db, [errand])
    await _attach_rated(db, [errand])
    return errand


async def cancel_errand(
    db: AsyncSession, redis: Redis, user: User, errand_id: uuid.UUID, reason: str | None
) -> Errand:
    errand = await db.scalar(select(Errand).where(Errand.id == errand_id).with_for_update())
    if errand is None or errand.deleted_at is not None or errand.campus_id != user.campus_id:
        raise ErrandError("Errand not found.", 404)

    is_requester = errand.requester_id == user.id
    is_runner = errand.runner_id == user.id
    if not (is_requester or is_runner):
        raise ErrandError("Only the requester or assigned runner can cancel.", 403)
    # A runner can back out before pickup (e.g. nothing was in stock) — but
    # once they've picked up, they must deliver.
    if is_runner and not is_requester and errand.status != "ACCEPTED":
        raise ErrandError("You can only cancel before pickup.", 409)

    _transition(errand, "CANCELLED")
    errand.cancelled_at = datetime.now(UTC)
    _record(db, errand, user, "CANCELLED", {"reason": reason} if reason else None)
    _emit_order_event(db, errand, "CANCELLED")
    # The ORDER_CANCELLED event notifies the runner; when the RUNNER is the one
    # backing out, tell the requester directly so they're not left waiting.
    if is_runner and not is_requester:
        from app.modules.notifications import service as notifications

        await notifications.create_and_push(
            db, redis, errand.requester_id,
            "ERRAND_CANCELLED_BY_RUNNER", "Runner couldn't complete it 😔",
            f"“{errand.title}” was cancelled"
            + (f": {reason}" if reason else "")
            + ". Nothing was charged — post it again if you like.",
            {"errand_id": str(errand.id)},
        )
    await db.commit()
    await db.refresh(errand)
    await publish_status(redis, errand)
    await _attach_secret_flags(db, [errand])
    return errand
