import json
import logging
import random
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from geoalchemy2 import WKTElement
from redis.asyncio import Redis
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.crypto import decrypt_str, encrypt_str
from app.modules.auth.models import User
from app.modules.errands.models import (
    CATEGORY_FULFILLMENT,
    Errand,
    ErrandEvent,
    ErrandHandoffSecret,
    ErrandItem,
    OfferLog,
    Rating,
)
from app.modules.errands.schemas import ErrandCreate
from app.modules.fraud import integrity as fraud_integrity
from app.modules.fraud import reputation as fraud_reputation
from app.modules.ledger import service as ledger
from app.modules.outbox import service as outbox
from app.modules.runners import service as runners_service
from app.modules.runners.models import RunnerProfile
from app.modules.social import service as social_service
from app.modules.vendors.models import MenuItem, Vendor

logger = logging.getLogger(__name__)

ACCEPT_LOCK_PREFIX = "errand:accept:"
ACCEPT_LOCK_TTL_SECONDS = 10

# Pub/sub channels: order-status pushes to watchers, offer pushes to runners.
STATUS_CHANNEL_PREFIX = "errand:status:"
OFFER_CHANNEL_PREFIX = "runner:offers:"
OFFER_RADIUS_M = 3000
OFFER_FANOUT = 5

# Social distance an errand is first offered within: friends and
# friends-of-friends. Wide enough that a student with a handful of friends has
# real coverage, narrow enough that "someone you know" still means something.
SOCIAL_TIER_1_HOPS = 2

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
            # When the transition happened. Consumers that age evidence need
            # this: without it every PAID edge the graph projection wrote
            # carried a null date, so circulation and ring detection could only
            # ever be all-time, and a pattern from a year ago weighed the same
            # as one from yesterday.
            "at": datetime.now(UTC).isoformat(),
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
    max_hops: int | None = None,
) -> int:
    """Push an offer to the nearest available runners (Redis GEO + pub/sub).

    `max_hops` restricts the offer to runners within that social distance of
    the requester. This is what makes social matching mean anything: every
    candidate is published to in the same loop, milliseconds apart, so merely
    *sorting* by trust would leave a free-for-all race that the nearest
    stranger usually wins. Withholding the offer from strangers for a while is
    the only thing that actually gives someone you know first refusal.

    Returns 0 when nobody is within `max_hops` — the caller decides whether to
    widen immediately (a student with no friends yet must not be stranded) or
    let the scheduler escalate on a timer.

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

    candidate_ids = [rid for rid, _ in nearby]

    # Don't re-pair a requester with someone they share an open collusion ring
    # with. Narrow on purpose: neither person is excluded from anything else,
    # and both keep taking work from the rest of campus at a rank cost only.
    # None means the lookup failed, and excludes nobody.
    co_ringed = await fraud_integrity.co_ringed_with(db, errand.requester_id, candidate_ids)
    if co_ringed:
        nearby = [(rid, dist) for rid, dist in nearby if rid not in co_ringed]
        if not nearby:
            logger.info(
                "errand %s: every nearby runner shares an open ring with the requester",
                errand.id,
            )
            return 0
        candidate_ids = [rid for rid, _ in nearby]

    scores = await _safe_scores(errand.requester_id, candidate_ids)
    reputations = await _reputations(db, candidate_ids)
    penalties = await fraud_integrity.penalties(db, candidate_ids)

    # A small fraction of rounds go out socially blind. See `should_explore`.
    exploring = should_explore()
    ranking_scores = None if exploring else scores
    nearby = _rank_with_scores(nearby, ranking_scores, reputations, penalties)

    # An exploring round ignores the hop ceiling too. Ranking without the boost
    # while still refusing to offer past 2 hops would not be a control group at
    # all — the strangers whose absence is the whole problem would still never
    # be offered anything, and the sample would stay exactly as biased.
    if max_hops is not None and scores is not None and not exploring:
        nearby = [(r, d) for r, d in nearby if scores.get(r, {}).get("hops", 99) <= max_hops]
        if not nearby:
            return 0

    # After filtering, so the log holds the set that was actually offered
    # rather than the set that was considered. `scores` (not `ranking_scores`)
    # is passed on purpose: the trust the graph reported is worth recording
    # even on a round that declined to act on it.
    await _record_offer_log(
        db,
        errand=errand,
        ranked=nearby,
        scores=scores,
        reputations=reputations,
        penalties=penalties,
        max_hops=None if exploring else max_hops,
        exploring=exploring,
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
        # The degree badge rides along with the offer. Friendship edges are
        # undirected, so requester→runner hops are the same number the runner
        # needs for "how do I know this person".
        payload["connection"] = _connection_payload(scores, runner_id)
        await redis.publish(f"{OFFER_CHANNEL_PREFIX}{runner_id}", json.dumps(payload))
    return len(nearby)


async def _safe_scores(requester_id: uuid.UUID, runner_ids: list[uuid.UUID]) -> dict | None:
    """Social scores for a candidate set, or None when the graph is unavailable.

    None and {} mean different things: {} is 'graph answered, nobody connected',
    None is 'no answer'. Only the former may be used to filter people out.
    """
    if not runner_ids:
        return {}
    try:
        return await social_service.social_scores(requester_id, runner_ids)
    except Exception:
        logger.warning("social scores unavailable", exc_info=True)
        return None


def _connection_payload(scores: dict | None, runner_id: uuid.UUID) -> dict:
    s = (scores or {}).get(runner_id)
    if not s:
        return {"degree": None, "label": "R", "via": None, "trust": 0.0}
    return {
        "degree": s["hops"],
        "label": social_service.degree_label(s["hops"]),
        "via": s.get("via"),
        "trust": s["trust"],
    }


# How far a full star of reputation can move a runner up the queue. Smaller
# than SOCIAL_WEIGHT_M on purpose: reputation should decide between comparable
# candidates, not let an excellent runner across campus beat a decent one at
# the door. Measured from NEUTRAL_REPUTATION, so this both rewards and demotes.
REPUTATION_WEIGHT_M = 800.0
NEUTRAL_REPUTATION = 3.5


def _rank_with_scores(
    nearby: list[tuple[uuid.UUID, float]],
    scores: dict | None,
    reputations: dict[uuid.UUID, float] | None = None,
    penalties: dict[uuid.UUID, float] | None = None,
) -> list[tuple[uuid.UUID, float]]:
    """Order candidates by distance, offset by trust, reputation and standing.

    Four terms, deliberately in the same unit — metres of effective distance —
    so their relative influence is legible rather than buried in a weighted sum
    of incomparable scales:

        effective = distance
                  - trust      x SOCIAL_WEIGHT_M
                  - (rep - 3.5) x REPUTATION_WEIGHT_M
                  + open-flag penalty (see fraud/integrity.py)

    The last term is the only one that adds: an unreviewed flag pushes a runner
    down the queue and can never pull them up it. It is also the only one
    bounded — capped so that accumulating suspicion can demote someone but
    never quietly amount to a ban.

    The reputation used is the PROVENANCE-WEIGHTED one, shrunk toward neutral
    when little independent evidence backs it. That is what closes the loop the
    price flags always implied but never had: a penalty lowers the score, the
    score lowers the ranking, and the runner is genuinely offered less work.
    Before this, a flagged runner lost a star and was offered exactly as much.
    """
    if len(nearby) < 2 or (not scores and not reputations and not penalties):
        return nearby

    def effective(item: tuple[uuid.UUID, float]) -> float:
        return _terms_for(item[0], item[1], scores, reputations, penalties)["effective"]

    return sorted(nearby, key=effective)


def _terms_for(
    runner_id: uuid.UUID,
    distance_m: float,
    scores: dict | None,
    reputations: dict[uuid.UUID, float] | None,
    penalties: dict[uuid.UUID, float] | None,
) -> dict[str, Any]:
    """The four terms behind one candidate's rank, and their sum.

    Single source of truth: ranking sorts on `effective` and the offer log
    stores the whole dict. Were the log to recompute the formula separately the
    two would drift, and a counterfactual built on a stale copy of the ranking
    rule is worse than no counterfactual at all.
    """
    social = (scores or {}).get(runner_id) or {}
    trust = float(social.get("trust", 0.0))
    rep = float((reputations or {}).get(runner_id, NEUTRAL_REPUTATION))
    penalty = float((penalties or {}).get(runner_id, 0.0))
    return {
        "runner_id": str(runner_id),
        "distance_m": round(float(distance_m), 1),
        "trust": round(trust, 4),
        "hops": social.get("hops"),
        "reputation": round(rep, 3),
        "penalty": round(penalty, 1),
        "effective": round(
            float(distance_m)
            - trust * SOCIAL_WEIGHT_M
            - (rep - NEUTRAL_REPUTATION) * REPUTATION_WEIGHT_M
            + penalty,
            1,
        ),
    }


def should_explore() -> bool:
    """Whether this dispatch round ignores friendship entirely.

    Errandly boosts friends up the offer queue and then reads "friends
    transacting with each other" as evidence of a collusion ring — so the
    router manufactures the signal the detector trusts. The stronger the boost
    the worse it gets: at the live weight the policy already expects almost
    every errand in a friend group to stay inside it, and once you expect
    everything, nothing can be surprising. A real ring stops being
    distinguishable from ordinary friendship, not because it hid but because
    the router does its work for it.

    So a slice of rounds is offered blind, keeping a control group in the data.
    It is a real cost — those requesters get a worse-matched runner — paid to
    keep collusion detectable at all.

    Read from settings on every call rather than captured at import, so the
    rate can be changed without a deploy and pinned to 0 in tests.
    """
    rate = settings.offer_explore_rate
    if rate <= 0:
        return False
    return random.random() < min(rate, 1.0)


async def _record_offer_log(
    db: AsyncSession,
    *,
    errand: Errand,
    ranked: list[tuple[uuid.UUID, float]],
    scores: dict | None,
    reputations: dict[uuid.UUID, float] | None,
    penalties: dict[uuid.UUID, float] | None,
    max_hops: int | None,
    exploring: bool = False,
) -> None:
    """Store why this offer round went out in the order it did.

    Best-effort by design. This is analytics: nothing reads it on a request
    path, so a failure here must cost an errand nothing. It runs in a SAVEPOINT
    so a bad write rolls back only itself and leaves the caller's transaction —
    which is in the middle of dispatching an errand — untouched.
    """
    if not ranked:
        return
    try:
        async with db.begin_nested():
            round_no = (
                await db.scalar(
                    select(func.count())
                    .select_from(OfferLog)
                    .where(OfferLog.errand_id == errand.id)
                )
            ) or 0
            db.add(
                OfferLog(
                    errand_id=errand.id,
                    requester_id=errand.requester_id,
                    campus_id=errand.campus_id,
                    round_no=round_no + 1,
                    max_hops=max_hops,
                    exploring=exploring,
                    candidates=[
                        {
                            **_terms_for(rid, dist, scores, reputations, penalties),
                            "rank": i,
                        }
                        for i, (rid, dist) in enumerate(ranked)
                    ],
                )
            )
    except Exception:
        logger.warning("offer log not written for errand %s", errand.id, exc_info=True)


async def mark_offer_accepted(
    db: AsyncSession, errand_id: uuid.UUID, runner_id: uuid.UUID
) -> None:
    """Stamp the taker onto the most recent offer round for this errand.

    Which round they accepted from matters: a runner who took an errand on the
    third, widened round was chosen under a different candidate set from one who
    took it immediately, and treating those as the same observation would bias
    exactly the estimate this table exists to support.
    """
    try:
        async with db.begin_nested():
            row = await db.scalar(
                select(OfferLog)
                .where(OfferLog.errand_id == errand_id)
                .order_by(OfferLog.created_at.desc())
                .limit(1)
            )
            if row is not None and row.accepted_runner_id is None:
                row.accepted_runner_id = runner_id
                row.accepted_at = datetime.now(UTC)
    except Exception:
        logger.warning("offer acceptance not recorded for %s", errand_id, exc_info=True)


async def _reputations(
    db: AsyncSession, runner_ids: list[uuid.UUID]
) -> dict[uuid.UUID, float]:
    """Provenance-weighted reputation per candidate, for ranking.

    Read from Postgres rather than recomputed here: the weighting needs a
    runner's whole rating history, which is far too much work for an offer
    that has to go out in milliseconds. It is refreshed when a rating lands.
    """
    if not runner_ids:
        return {}
    rows = await db.execute(
        select(User.id, User.effective_reputation).where(User.id.in_(runner_ids))
    )
    return {uid: float(rep) for uid, rep in rows}


# How much social trust can outweigh distance. At 1500 a direct friend
# (trust 1.0) beats a stranger who is up to 1.5km closer, while a 3-hop
# acquaintance (trust ~0.2) only wins ties inside ~300m. Tuned so the graph
# reorders realistic candidate sets without ever sending an errand across
# campus to reach a friend.
SOCIAL_WEIGHT_M = 1500.0


async def _rank_by_social_trust(
    requester_id: uuid.UUID, nearby: list[tuple[uuid.UUID, float]]
) -> list[tuple[uuid.UUID, float]]:
    """Reorder spatial candidates so socially-closer runners are offered first.

    Candidate *generation* stays purely spatial — the graph never widens the
    set, it only reorders it, so a well-connected student cannot pull errands
    from across campus. Ranking is by effective distance:

        effective = distance_m − trust × SOCIAL_WEIGHT_M

    If the graph is unavailable `social_scores` returns {}, every candidate
    scores 0, and this degrades to exactly the distance ordering Redis gave us.
    That is the intended failure mode: matching gets worse, never broken.
    """
    if len(nearby) < 2:
        return nearby
    try:
        scores = await social_service.social_scores(requester_id, [rid for rid, _ in nearby])
    except Exception:
        logger.warning("social ranking unavailable; using distance order", exc_info=True)
        return nearby
    if not scores:
        return nearby

    def effective(item: tuple[uuid.UUID, float]) -> float:
        runner_id, distance_m = item
        trust = scores.get(runner_id, {}).get("trust", 0.0)
        return distance_m - trust * SOCIAL_WEIGHT_M

    ranked = sorted(nearby, key=effective)
    friends = sum(1 for rid, _ in ranked if scores.get(rid, {}).get("hops") == 1)
    logger.info(
        "social ranking: %d/%d candidates connected (%d direct friends)",
        len(scores),
        len(nearby),
        friends,
    )
    return ranked


async def _within_hops(
    requester_id: uuid.UUID, nearby: list[tuple[uuid.UUID, float]], max_hops: int
) -> list[tuple[uuid.UUID, float]]:
    """Keep only candidates within `max_hops` friendship hops of the requester.

    Returns the list unfiltered when the graph is unavailable. Failing open is
    deliberate: a graph outage should make matching less socially targeted, not
    stop errands from being offered at all.
    """
    try:
        scores = await social_service.social_scores(requester_id, [rid for rid, _ in nearby])
    except Exception:
        logger.warning("hop filter unavailable; offering to all candidates", exc_info=True)
        return nearby
    if not scores:
        return []
    return [(rid, d) for rid, d in nearby if scores.get(rid, {}).get("hops", 99) <= max_hops]


async def attach_connections(viewer: User, errands: list[Errand]) -> None:
    """Set .connection on each errand: how the viewer relates to the OTHER party.

    Which party that is depends on who is looking. A runner browsing the feed
    wants to know how they connect to the requester; a requester looking at
    their own errand wants the runner. Showing someone their connection to
    themselves would be noise, so own-errand rows with no runner get nothing.

    Never raises: a graph outage drops the badge, it does not break the feed.
    """
    if not errands:
        return
    others: dict[uuid.UUID, uuid.UUID] = {}
    for e in errands:
        other = e.runner_id if e.requester_id == viewer.id else e.requester_id
        if other and other != viewer.id:
            others[e.id] = other
    if not others:
        return
    try:
        found = await social_service.connections_for(viewer.id, list(others.values()))
    except Exception:
        logger.warning("connection badges unavailable", exc_info=True)
        return
    stranger = {"degree": None, "label": "R", "via": None, "trust": 0.0}
    for e in errands:
        other = others.get(e.id)
        if other:
            e.connection = found.get(other, stranger)


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
    # Carrying a run commits you to it. Both clients lock the Order/Run toggle,
    # but a client-side lock is a courtesy, not a control — anyone with devtools
    # or curl walks straight through it. The rule is enforced here, where every
    # client gets it and none can bypass it.
    #
    # Deliberately one-directional: having placed an order never stops you
    # taking a run. It is the accepted delivery that someone else is waiting
    # on, so that is the only thing that locks.
    if await runners_service.active_load(db, user.id) > 0:
        raise ErrandError(
            "Finish or release the run you're on before ordering.",
            409,
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

    # Escrow the requester's money BEFORE the errand is offered to anyone. A
    # runner who fronts cash at the counter is relying on this hold existing —
    # an unfunded order must never reach the feed.
    #
    # Only catalog lines carry a price; hand-typed list lines are deliberately
    # priceless, and collect_amount is what covers those. It is already part of
    # the hold, so a shopping-list errand is still fully funded up front.
    items_total = sum(
        Decimal(str(i.unit_price_snapshot)) * i.quantity for i in order_items
    )
    try:
        await ledger.place_hold(
            db,
            errand_id=errand.id,
            requester_id=user.id,
            items_total=items_total,
            reward=Decimal(str(data.reward)),
            collect_amount=Decimal(str(data.collect_amount)),
        )
    except ledger.LedgerError as e:
        await db.rollback()
        raise ErrandError(e.message, e.status_code) from e

    if data.otp:
        db.add(ErrandHandoffSecret(errand_id=errand.id, otp_ciphertext=encrypt_str(data.otp)))
    _record(db, errand, user, "CREATED", {"category": data.category, "reward": data.reward})
    _emit_order_event(db, errand, "CREATED")
    await db.commit()
    await db.refresh(errand)

    # Tier 1: friends and friends-of-friends only. The scheduler widens this on
    # a timer (see SOCIAL_TIERS in workers/consumers.py) so nobody waits long.
    offered = await _offer_to_nearby_runners(db, redis, errand, max_hops=SOCIAL_TIER_1_HOPS)
    tier = 1
    if not offered:
        # Nobody you know is nearby — or you have no friends yet, which is every
        # student on day one. Falling straight through to an open offer matters
        # more than the social preference does: an errand nobody sees is worse
        # than an errand a stranger takes.
        offered = await _offer_to_nearby_runners(db, redis, errand)
        tier = 0
    if offered:
        _record(db, errand, None, "OFFERED", {"runners": offered, "social_tier": tier})
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
    await attach_connections(user, errands)
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
    await attach_connections(user, requested + running)
    return requested, running


async def get_errand(db: AsyncSession, user: User, errand_id: uuid.UUID) -> Errand:
    """One errand, if this user is allowed to see it.

    Campus membership alone used to be the whole check, which meant any student
    could fetch any errand on campus by id and read its requester, its assigned
    runner, its progress, its items and its amounts — including runs they had
    no part in and errands that finished months ago.

    The rule is narrower: you see your own errands, and you see work that is
    still open. An OPEN errand is an offer to the campus, so a runner deciding
    whether to take it legitimately needs to read it. Once someone else has
    accepted, it stops being an offer and becomes two people's business.

    404 rather than 403, because confirming that an errand exists is itself
    something a stranger should not learn.
    """
    errand = await db.get(Errand, errand_id)
    if errand is None or errand.deleted_at is not None or errand.campus_id != user.campus_id:
        raise ErrandError("Errand not found.", 404)

    is_party = user.id in (errand.requester_id, errand.runner_id)
    if not is_party and errand.status != "OPEN" and user.role != "ADMIN":
        raise ErrandError("Errand not found.", 404)
    await _attach_secret_flags(db, [errand])
    await _attach_items(db, [errand])
    await _attach_rated(db, [errand])
    await attach_connections(user, [errand])
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
        # Close the loop on the offer round this runner took: without the
        # outcome the candidate set is a question with no answer.
        await mark_offer_accepted(db, errand.id, user.id)
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
    # The plain average above is what the runner sees. Ranking reads the
    # provenance-weighted figure, refreshed here so the offer path never has to
    # recompute a whole rating history.
    await db.flush()
    await fraud_reputation.recompute(db, runner.id)
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
    await attach_connections(user, [errand])
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
    # Escrow returns to the requester in the same transaction as the state
    # change — a cancelled order that quietly keeps someone's money is the
    # bug this ordering exists to make impossible.
    await ledger.refund_hold(db, errand_id=errand.id, memo="Order cancelled")
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
