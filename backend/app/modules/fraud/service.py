"""Price-claim judgement, and what happens to people who keep failing it.

The shape of the thing:

    runner submits what they paid
        -> normalize the item name so it groups with its peers
        -> compare against the campus reference for that item
        -> OK / FLAGGED / NO_REFERENCE, frozen as a snapshot on the claim
        -> only the ELIGIBLE amount is ever reimbursed
        -> a pattern of flags, not a single flag, triggers punishment

That last line is the important one. One high claim is not fraud; puffs really
do cost more at the far canteen some days. "Constantly quoting higher" is a
pattern, so the ladder keys off a count over a window, and a single bad day
costs a runner nothing.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from statistics import median
from typing import NamedTuple

from redis.asyncio import Redis
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.modules.auth.models import User
from app.modules.errands.models import Errand, Rating
from app.modules.fraud import collusion, estimator, reputation, semantics
from app.modules.fraud import normalize as normalize_mod
from app.modules.fraud.models import (
    STRIKE_ACTIONS,
    FraudFlag,
    ItemAlias,
    ReferencePrice,
    ReferencePriceProposal,
    RunnerPriceClaim,
    UserStrike,
)
from app.modules.fraud.normalize import resolve_key
from app.modules.ledger import service as ledger
from app.modules.notifications import service as notifications
from app.modules.runners.models import RunnerProfile

logger = logging.getLogger(__name__)

TWO_PLACES = Decimal("0.01")

# The allowance scales with the item. A flat rupee line cannot work across a
# canteen menu: 20 rupees is +80% on a 25-rupee puff and +4% on a 500-rupee
# grocery run, so cheap items - which are most of the traffic - were barely
# protected. Measured before this change, a 10-rupee tea claimed at 29 (+190%)
# was paid in full.
#
# So the allowance is a share of the reference, bounded at both ends:
#
#     tolerance = clamp(reference x tolerance_pct, MIN_TOLERANCE_ABS, tolerance_abs)
#
# The floor keeps very cheap items from having a near-zero allowance that any
# rounding would trip. The ceiling is `tolerance_abs`, whose meaning changes
# from "the line" to "the most the line may ever be" - so a large grocery run
# behaves exactly as it did before.
MIN_TOLERANCE_ABS = Decimal("5.00")

# --- per-store adjustment ---------------------------------------------------
# The campus reference answers "what does this item cost here", but an item does
# not have one price: it is 23 at one canteen and 30 at another. A single median
# lands in the gap and is wrong in both directions - the honest runner at the
# dearer shop looks permanently elevated, and the runner inflating at the
# cheaper one looks normal.
#
# So the reference is nudged toward what that store is actually observed to
# charge, shrunk by how much evidence exists for it:
#
#     ref_store = w x median(store claims) + (1 - w) x campus_reference
#     w         = n / (n + STORE_PRIOR)
#
# Partial pooling rather than a separate reference per store: splitting outright
# would fragment small samples until almost everything fell back to
# NO_REFERENCE. With two observations the store barely moves the number; with
# twenty it mostly decides it. Same shrinkage the reputation module uses for
# rating confidence.
#
# Verdict is deliberately NOT filtered here, and that took a wrong turn first.
# Excluding FLAGGED claims - the obvious rule, and the right one for the campus
# estimator - deadlocks a genuinely dear shop: every honest claim at its real
# price is flagged against the campus number, so no unflagged evidence can ever
# accumulate and the store stays permanently mispriced. Measured: four honest
# runners reporting 30 at a 20-reference item moved the store estimate not at
# all.
#
# What keeps this safe is not the verdict filter but INDEPENDENCE. One runner
# claiming 30 two hundred times contributes one 30, exactly as in the campus
# estimator; the store only moves when several different runners agree, which a
# lone inflater cannot manufacture. A ring of colluding runners could - and that
# is what the collusion graph is for, not this.
STORE_PRIOR = Decimal("6")
# Distinct runners, not claims. This is the whole defence.
STORE_MIN_RUNNERS = 3
# Never let the store adjustment stray further than this from the campus
# reference. A store cannot be talked into being three times dearer than campus
# by its own claim history, however many claims it has.
STORE_MAX_DRIFT = Decimal("0.60")


def _store_label(store_key: str | None) -> str | None:
    """The store key as a human would read it. Vendor ids stay opaque here;
    the admin console resolves those from its own vendor list."""
    if not store_key:
        return None
    if store_key.startswith("label:"):
        return store_key[len("label:") :].title()
    return store_key


def store_key_for(errand) -> str | None:
    """Which outlet an errand's purchases come from.

    A vendor id when the errand named one; otherwise the pickup label the
    requester typed, normalized so "Main Canteen" and "main canteen " are the
    same store.
    """
    if getattr(errand, "vendor_id", None):
        return f"vendor:{errand.vendor_id}"
    label = (getattr(errand, "pickup_label", None) or "").strip().lower()
    return f"label:{normalize_mod.normalize(label)}"[:120] if label else None

# How far back a flag counts against someone. Old mistakes stop mattering -
# a permanent record for one bad week would be punishment without end.
PATTERN_WINDOW_DAYS = 30

# Flags-in-window required to reach each strike level. Level 1 needs THREE
# separate flagged errands: that is what makes it a pattern rather than an
# accident, and it is the difference between this system and one that punishes
# a runner for paying 5 rupees extra once.
STRIKE_THRESHOLDS = (3, 5, 8, 12)

# Reputation lost at strike level 2.
REPUTATION_PENALTY = Decimal("0.50")
# How long a fraud block keeps a runner from going online.
RUNNER_BLOCK_DAYS = 7

# Claim-vs-reference overshoot, in rupees over the line -> flag severity.
SEVERITY_BANDS = ((Decimal("20"), 1), (Decimal("50"), 2))

# --- "walking the line" detection -------------------------------------------
# A flat rupee threshold is easy to understand and easy to game: quote ₹19 over
# every time and never trip it once. So elevated-but-legal claims are counted
# too, and a runner whose claims *cluster* just under the line gets flagged on
# the pattern even though no single claim broke a rule.
#
# This deliberately does NOT withhold money — nothing was proven about any one
# claim. It raises the pattern for an admin to look at.
NEAR_THRESHOLD_SHARE = Decimal("0.60")   # >=60% of the way to the line = "near"
NEAR_THRESHOLD_MIN_CLAIMS = 4            # near-line claims needed in the window
NEAR_THRESHOLD_MIN_RATIO = Decimal("0.60")  # share of their judged claims

# Unpriced names to ask about per sweep. Small on purpose: the recurring
# ones surface first, and a cap keeps a burst of typos from becoming a bill.
ALIAS_SUGGESTIONS_PER_SWEEP = 5


class FraudError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def _money(value) -> Decimal:
    return Decimal(str(value or 0)).quantize(TWO_PLACES)


def _severity(delta_pct: Decimal) -> int:
    for ceiling, level in SEVERITY_BANDS:
        if delta_pct <= ceiling:
            return level
    return 3


# --------------------------------------------------------------- reference


async def known_keys(db: AsyncSession, campus_id: uuid.UUID) -> list[str]:
    rows = await db.execute(
        select(ReferencePrice.item_key).where(ReferencePrice.campus_id == campus_id)
    )
    return [r[0] for r in rows]


async def approved_aliases(db: AsyncSession, campus_id: uuid.UUID) -> dict[str, str]:
    """Admin-approved name equivalences, as {alias_key: item_key}.

    PENDING rows are excluded on purpose - a suggestion nobody has confirmed
    must not change what anyone is judged against.
    """
    rows = await db.execute(
        select(ItemAlias.alias_key, ItemAlias.item_key).where(
            ItemAlias.campus_id == campus_id, ItemAlias.status == "APPROVED"
        )
    )
    return {a: i for a, i in rows}


async def suggest_item_aliases(db: AsyncSession, campus_id: uuid.UUID) -> list[ItemAlias]:
    """Ask the model whether recently-unpriced item names mean something known.

    Runs on a timer, never in the claim request path. A runner standing at a
    counter must not wait on a model call, and asking once per claim would pay
    for the same question repeatedly - the names that matter are the ones that
    keep recurring, and a batch sweep sees exactly those.

    Everything produced here is PENDING. Nothing is judged against it until an
    admin agrees.
    """
    since = datetime.now(UTC) - timedelta(days=PATTERN_WINDOW_DAYS)
    keys = await known_keys(db, campus_id)
    if not keys:
        return []

    # Names that were claimed but matched nothing. Ordered by how often they
    # recur, so a one-off typo never costs a model call while a genuine missing
    # alias rises to the top on its own.
    rows = await db.execute(
        select(
            RunnerPriceClaim.item_key,
            func.min(RunnerPriceClaim.raw_name),
            func.count().label("seen"),
        )
        .where(
            RunnerPriceClaim.campus_id == campus_id,
            RunnerPriceClaim.created_at >= since,
            RunnerPriceClaim.verdict == "NO_REFERENCE",
        )
        .group_by(RunnerPriceClaim.item_key)
        .order_by(func.count().desc())
        .limit(ALIAS_SUGGESTIONS_PER_SWEEP)
    )
    candidates = [(k, raw, n) for k, raw, n in rows if k and k not in keys]
    if not candidates:
        return []

    # Skip anything already decided or already proposed.
    seen_keys = set(
        (
            await db.scalars(
                select(ItemAlias.alias_key).where(
                    ItemAlias.campus_id == campus_id,
                    ItemAlias.alias_key.in_([c[0] for c in candidates]),
                )
            )
        ).all()
    )

    created: list[ItemAlias] = []
    for alias_key, raw_name, _seen in candidates:
        if alias_key in seen_keys:
            continue
        target = await normalize_mod.suggest_alias(raw_name, keys)
        if not target or target == alias_key:
            continue
        row = ItemAlias(
            campus_id=campus_id,
            alias_key=alias_key,
            item_key=target,
            sample_raw_name=raw_name[:120],
            reason=f"Model matched '{raw_name}' to '{target}'.",
            source="MODEL",
            status="PENDING",
        )
        db.add(row)
        created.append(row)

    if created:
        await db.flush()
        logger.info("alias sweep proposed %d alias(es) for review", len(created))
    return created


async def get_reference(
    db: AsyncSession, campus_id: uuid.UUID, item_key: str
) -> ReferencePrice | None:
    return await db.scalar(
        select(ReferencePrice).where(
            ReferencePrice.campus_id == campus_id, ReferencePrice.item_key == item_key
        )
    )


class Judgement(NamedTuple):
    verdict: str
    delta_abs: Decimal | None
    delta_pct: Decimal | None
    threshold: Decimal | None
    eligible: Decimal


async def store_adjusted_reference(
    db: AsyncSession,
    campus_id: uuid.UUID,
    item_key: str,
    store_key: str | None,
    reference: ReferencePrice,
) -> Decimal:
    """The campus reference, moved toward what this store actually charges.

    Returns the campus reference unchanged when the store is unknown or barely
    observed, so a new outlet is judged by campus prices until it has a record
    of its own.
    """
    base = _money(reference.reference_price)
    if not store_key:
        return base

    rows = await db.execute(
        select(RunnerPriceClaim.runner_id, RunnerPriceClaim.claimed_unit_price).where(
            RunnerPriceClaim.campus_id == campus_id,
            RunnerPriceClaim.item_key == item_key,
            RunnerPriceClaim.store_key == store_key,
        )
    )
    by_runner: dict[uuid.UUID, list[Decimal]] = {}
    for runner_id, price in rows:
        by_runner.setdefault(runner_id, []).append(Decimal(str(price)))
    if len(by_runner) < STORE_MIN_RUNNERS:
        return base

    # One runner, one vote: their own median first, then the median across
    # runners, so volume from a single reporter buys no influence.
    per_runner = [Decimal(str(median(v))) for v in by_runner.values()]
    observed = Decimal(str(median(per_runner)))
    n = Decimal(len(by_runner))
    w = n / (n + STORE_PRIOR)
    blended = _money(w * observed + (Decimal("1") - w) * base)

    # Clamp the drift so a store's own history cannot carry it arbitrarily far.
    lo = _money(base * (Decimal("1") - STORE_MAX_DRIFT))
    hi = _money(base * (Decimal("1") + STORE_MAX_DRIFT))
    return max(lo, min(blended, hi))


def effective_tolerance(reference: ReferencePrice) -> Decimal:
    """How far above the reference a single claim may sit before it is flagged.

    A share of the item's own price, floored so cheap items keep a usable
    allowance and capped by the admin's `tolerance_abs` so an expensive item
    does not acquire an enormous one.
    """
    pct = Decimal(str(reference.tolerance_pct or 0))
    ceiling = _money(reference.tolerance_abs)
    if pct <= 0:
        return ceiling  # percentage disabled for this item: the old behaviour
    scaled = _money(Decimal(str(reference.reference_price)) * pct)
    return max(MIN_TOLERANCE_ABS, min(scaled, ceiling))


def judge(
    claimed_unit_price: Decimal,
    quantity: int,
    reference: ReferencePrice | None,
    ref_override: Decimal | None = None,
) -> Judgement:
    """Judge one claimed line against the campus reference.

    More than the allowance over the reference is flagged outright and the
    excess withheld; between the reference and that line the claim is paid in
    full but recorded as ELEVATED, because where a runner habitually sits
    inside the allowance is itself evidence.

    The allowance scales with the item price - see MIN_TOLERANCE_ABS above for
    why a flat line could not work.

    With no reference we cannot call anything fraud - an unpriced item is our
    gap, not the runner's. The claim is paid and becomes evidence toward the
    reference that will judge the next one.
    """
    claimed_unit_price = _money(claimed_unit_price)
    claimed_total = _money(claimed_unit_price * quantity)

    if reference is None:
        return Judgement("NO_REFERENCE", None, None, None, claimed_total)

    # The store-adjusted value when the caller computed one, else the campus
    # reference. The allowance still scales off the ADMIN reference, not the
    # adjusted one, so a store cannot widen its own allowance by being dear.
    ref_unit = _money(ref_override) if ref_override is not None else _money(reference.reference_price)
    if ref_unit <= 0:
        return Judgement("NO_REFERENCE", None, None, None, claimed_total)

    threshold = effective_tolerance(reference)
    delta_abs = _money(claimed_unit_price - ref_unit)
    delta_pct = ((claimed_unit_price - ref_unit) / ref_unit * 100).quantize(TWO_PLACES)

    if delta_abs > threshold:
        # Flagged: reimburse what the item is known to cost, withhold the
        # excess. Refusing to pay an unproven excess is not a punishment - it
        # is simply not paying for something nobody can show was spent.
        return Judgement(
            "FLAGGED", delta_abs, delta_pct, threshold, _money(ref_unit * quantity)
        )

    if delta_abs > 0:
        # Paid in full. Counted, not punished.
        return Judgement("ELEVATED", delta_abs, delta_pct, threshold, claimed_total)

    return Judgement("OK", delta_abs, delta_pct, threshold, claimed_total)


# ------------------------------------------------------------------ claims


async def submit_claims(
    db: AsyncSession,
    redis: Redis,
    *,
    errand: Errand,
    runner: User,
    lines: list[tuple[str, Decimal, int]],
) -> list[RunnerPriceClaim]:
    """Record what a runner says they paid, and judge each line.

    Called at pickup, before delivery - the claim has to exist before the money
    moves, or the fraud check has nothing to check.
    """
    if errand.runner_id != runner.id:
        raise FraudError("Only the assigned runner can report prices.", 403)
    if errand.status not in ("ACCEPTED", "IN_PROGRESS"):
        raise FraudError("Prices can only be reported during an active run.", 409)
    if not lines:
        raise FraudError("No price lines submitted.", 422)

    keys = await known_keys(db, errand.campus_id)
    aliases = await approved_aliases(db, errand.campus_id)
    store_key = store_key_for(errand)
    claims: list[RunnerPriceClaim] = []

    for raw_name, unit_price, quantity in lines:
        item_key, _matched = resolve_key(raw_name, keys, aliases)
        if not item_key:
            raise FraudError(f"Could not read an item name from '{raw_name}'.", 422)

        reference = await get_reference(db, errand.campus_id, item_key)
        ref_unit = (
            await store_adjusted_reference(
                db, errand.campus_id, item_key, store_key, reference
            )
            if reference
            else None
        )
        j = judge(unit_price, quantity, reference, ref_override=ref_unit)

        existing = await db.scalar(
            select(RunnerPriceClaim).where(
                RunnerPriceClaim.errand_id == errand.id,
                RunnerPriceClaim.item_key == item_key,
            )
        )
        # Snapshot the value actually judged against, not the campus one, so an
        # admin reviewing the flag sees the number the runner was held to.
        ref_snapshot = _money(ref_unit) if ref_unit is not None else None
        if existing is None:
            claim = RunnerPriceClaim(
                errand_id=errand.id,
                runner_id=runner.id,
                campus_id=errand.campus_id,
                raw_name=raw_name[:120],
                item_key=item_key,
                store_key=store_key,
                claimed_unit_price=_money(unit_price),
                quantity=quantity,
                reference_snapshot=ref_snapshot,
                threshold_snapshot=j.threshold,
                delta_pct=j.delta_pct,
                delta_abs=j.delta_abs,
                verdict=j.verdict,
                eligible_amount=j.eligible,
            )
            db.add(claim)
        else:
            claim = existing
            claim.raw_name = raw_name[:120]
            claim.claimed_unit_price = _money(unit_price)
            claim.quantity = quantity
            claim.reference_snapshot = ref_snapshot
            claim.threshold_snapshot = j.threshold
            claim.delta_pct = j.delta_pct
            claim.delta_abs = j.delta_abs
            claim.verdict = j.verdict
            claim.eligible_amount = j.eligible

        await db.flush()
        claims.append(claim)

        if j.verdict == "FLAGGED":
            await raise_flag(
                db,
                user_id=runner.id,
                errand_id=errand.id,
                claim=claim,
                rule="CLAIM_ABOVE_REFERENCE",
                delta_pct=j.delta_abs or Decimal("0"),
            )

    # Someone whose claims cluster just under the line never trips the rule
    # above, so check that separately - and check it whether or not anything
    # was flagged today, since the whole point is that nothing ever is.
    await evaluate_near_threshold(db, errand.campus_id, runner)

    # Judge the pattern once per submission, not once per line - three inflated
    # lines on one receipt is one bad errand, not three strikes.
    if any(c.verdict == "FLAGGED" for c in claims):
        await evaluate_pattern(db, redis, runner)

    return claims


async def eligible_reimbursement(db: AsyncSession, errand_id: uuid.UUID) -> tuple[Decimal, Decimal]:
    """(eligible, withheld) across every claim on an errand."""
    rows = await db.execute(
        select(
            func.coalesce(func.sum(RunnerPriceClaim.eligible_amount), 0),
            func.coalesce(
                func.sum(RunnerPriceClaim.claimed_unit_price * RunnerPriceClaim.quantity), 0
            ),
        ).where(RunnerPriceClaim.errand_id == errand_id)
    )
    eligible, claimed = rows.one()
    eligible = _money(eligible)
    claimed = _money(claimed)
    return eligible, _money(max(claimed - eligible, Decimal("0")))


# ------------------------------------------------------------------- flags


async def raise_flag(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    errand_id: uuid.UUID | None,
    claim: RunnerPriceClaim | None,
    rule: str,
    delta_pct: Decimal,
    details: dict | None = None,
) -> FraudFlag:
    flag = FraudFlag(
        user_id=user_id,
        errand_id=errand_id,
        claim_id=claim.id if claim else None,
        rule=rule,
        severity=_severity(delta_pct),
        details=details
        or {
            "item": claim.item_key if claim else None,
            "claimed": float(claim.claimed_unit_price) if claim else None,
            # The value actually judged against, which is the store-adjusted
            # reference when that shop has a record of its own.
            "reference": float(claim.reference_snapshot)
            if claim and claim.reference_snapshot
            else None,
            # Which shop, so an admin can tell an inflated claim from an
            # honest one at a dearer counter. Without it they would be
            # reviewing with strictly less information than the system used
            # to raise the flag.
            "store": _store_label(claim.store_key) if claim else None,
            "delta_pct": float(delta_pct),
        },
    )
    db.add(flag)
    await db.flush()
    return flag


async def evaluate_near_threshold(
    db: AsyncSession, campus_id: uuid.UUID, runner: User
) -> FraudFlag | None:
    """Flag a runner whose claims habitually sit just under the rupee line.

    A flat threshold is honest and legible, but it is also a target: quote ₹19
    over on a ₹20 line every single time and no individual claim ever breaks a
    rule. What gives it away is the *distribution* - real prices scatter around
    the reference, while someone working the allowance clusters against it.

    So: count the claims in the window that landed in the top of the allowance,
    and flag when they are both numerous and the runner's normal behaviour.
    Requiring a high SHARE as well as a high COUNT is what keeps a busy honest
    runner out of it - they accumulate elevated claims too, but they also
    accumulate ordinary ones, and the ratio stays low.

    Raises a flag only; no money is withheld, because nothing has been shown
    about any single claim.
    """
    since = datetime.now(UTC) - timedelta(days=PATTERN_WINDOW_DAYS)

    rows = await db.execute(
        select(RunnerPriceClaim.delta_abs, RunnerPriceClaim.threshold_snapshot).where(
            RunnerPriceClaim.runner_id == runner.id,
            RunnerPriceClaim.campus_id == campus_id,
            RunnerPriceClaim.created_at >= since,
            RunnerPriceClaim.threshold_snapshot.is_not(None),
            # A claim already flagged outright is counted by the other rule;
            # counting it here too would punish one act twice.
            RunnerPriceClaim.verdict != "FLAGGED",
        )
    )
    judged = [(_money(d), _money(t)) for d, t in rows if t and _money(t) > 0]
    if not judged:
        return None

    near = [d for d, t in judged if d >= (t * NEAR_THRESHOLD_SHARE)]
    if len(near) < NEAR_THRESHOLD_MIN_CLAIMS:
        return None

    ratio = Decimal(len(near)) / Decimal(len(judged))
    if ratio < NEAR_THRESHOLD_MIN_RATIO:
        return None

    # One open flag per runner for this rule at a time - the pattern is one
    # ongoing observation, not a fresh accusation on every submission.
    already = await db.scalar(
        select(func.count())
        .select_from(FraudFlag)
        .where(
            FraudFlag.user_id == runner.id,
            FraudFlag.rule == "PERSISTENT_NEAR_THRESHOLD",
            FraudFlag.status == "OPEN",
        )
    )
    if already:
        return None

    avg_over = (sum(near) / Decimal(len(near))).quantize(TWO_PLACES)
    flag = FraudFlag(
        user_id=runner.id,
        rule="PERSISTENT_NEAR_THRESHOLD",
        severity=2,
        details={
            "near_line_claims": len(near),
            "judged_claims": len(judged),
            "share": float(ratio.quantize(TWO_PLACES)),
            "avg_rupees_over": float(avg_over),
            "window_days": PATTERN_WINDOW_DAYS,
        },
    )
    db.add(flag)
    await db.flush()
    return flag


async def count_recent_flags(db: AsyncSession, user_id: uuid.UUID) -> int:
    """Flagged ERRANDS in the window, not flagged lines.

    Counting distinct errands is deliberate: a receipt with four inflated items
    is one occasion of dishonesty, and counting it as four would race a runner
    up the ladder for a single incident.
    """
    since = datetime.now(UTC) - timedelta(days=PATTERN_WINDOW_DAYS)
    count = await db.scalar(
        select(func.count(func.distinct(func.coalesce(FraudFlag.errand_id, FraudFlag.id)))).where(
            FraudFlag.user_id == user_id,
            FraudFlag.created_at >= since,
            FraudFlag.status.in_(("OPEN", "UPHELD")),
        )
    )
    return count or 0


# -------------------------------------------------------------- punishment


def _level_for(flag_count: int) -> int:
    level = 0
    for threshold in STRIKE_THRESHOLDS:
        if flag_count >= threshold:
            level += 1
    return level


async def evaluate_pattern(
    db: AsyncSession, redis: Redis, runner: User
) -> UserStrike | None:
    """Escalate if this runner has crossed into a new strike level.

    Idempotent by construction: the level is a function of the flag count, and
    a strike is written only when that level exceeds the strikes already on
    file. Re-running this can never double-punish.
    """
    flag_count = await count_recent_flags(db, runner.id)
    target_level = _level_for(flag_count)
    if target_level == 0:
        return None

    current_level = (
        await db.scalar(
            select(func.count()).select_from(UserStrike).where(UserStrike.user_id == runner.id)
        )
        or 0
    )
    if target_level <= current_level:
        return None

    level = current_level + 1
    action = STRIKE_ACTIONS[min(level, len(STRIKE_ACTIONS)) - 1]
    reason = (
        f"{flag_count} price claims above the campus reference in the last "
        f"{PATTERN_WINDOW_DAYS} days."
    )
    strike = UserStrike(
        user_id=runner.id,
        level=level,
        action=action,
        reason=reason,
        expires_at=(
            datetime.now(UTC) + timedelta(days=RUNNER_BLOCK_DAYS)
            if action == "RUNNER_SUSPENDED"
            else None
        ),
    )
    db.add(strike)
    await _apply_action(db, redis, runner, action, strike)
    await db.flush()
    return strike


async def _apply_action(
    db: AsyncSession, redis: Redis, runner: User, action: str, strike: UserStrike
) -> None:
    """Carry out a strike. Every branch tells the runner what happened and why -
    a punishment nobody can see is just a system quietly breaking for them."""
    title, body = "", ""

    if action == "WARNING":
        title = "Price reports under review"
        body = (
            "Several of your reported prices came in above the campus reference. "
            "Please report exactly what you paid - keep receipts where you can."
        )

    elif action == "REPUTATION_PENALTY":
        runner.reputation_score = max(
            Decimal("0"), _money(runner.reputation_score) - REPUTATION_PENALTY
        )
        title = "Rating reduced"
        body = (
            f"Your rating dropped by {REPUTATION_PENALTY} after repeated over-reported "
            "prices. You will be offered fewer runs."
        )

    elif action == "RUNNER_SUSPENDED":
        profile = await db.get(RunnerProfile, runner.id)
        if profile:
            profile.is_available = False
            profile.fraud_blocked_until = strike.expires_at
            await redis.zrem(f"runners:geo:{profile.campus_id}", str(runner.id))
        title = "Running paused"
        body = (
            f"You cannot take runs for {RUNNER_BLOCK_DAYS} days due to repeated "
            "over-reported prices. Contact an admin if you believe this is wrong."
        )

    elif action == "ACCOUNT_SUSPENDED":
        runner.account_status = "SUSPENDED"
        profile = await db.get(RunnerProfile, runner.id)
        if profile:
            profile.is_available = False
            await redis.zrem(f"runners:geo:{profile.campus_id}", str(runner.id))
        title = "Account suspended"
        body = "Your account is suspended for repeated price fraud. Contact an admin."

    await notifications.create_and_push(
        db, redis, runner.id, "FRAUD_ACTION", title, body, {"action": action}
    )


async def active_runner_block(db: AsyncSession, user_id: uuid.UUID) -> datetime | None:
    """When a fraud block is in force, the moment it lifts. Otherwise None."""
    profile = await db.get(RunnerProfile, user_id)
    if profile is None or profile.fraud_blocked_until is None:
        return None
    return profile.fraud_blocked_until if profile.fraud_blocked_until > datetime.now(UTC) else None


# ------------------------------------------------------- collusion rings


async def sweep_collusion_rings(db: AsyncSession) -> list[FraudFlag]:
    """Find closed money cycles and raise a flag per member.

    Runs on a timer rather than on each settlement: a ring only becomes visible
    after several completed errands, so there is nothing to see at the moment
    any one of them settles, and re-running the cycle search per payout would
    be pure cost.

    Every member of a detected cycle is flagged, not just one. A ring has no
    ringleader visible from the graph — the shape is symmetric, and picking a
    "primary" would be inventing a fact. An admin reviewing them sees the whole
    group and decides.

    No money is withheld here. A cycle is strong evidence about a *group*, but
    it says nothing about which specific errand was dishonest, and the escrow
    holds it would touch have long since settled. It gates matching and asks a
    human; it does not reach into a wallet.
    """
    rings = await collusion.find_rings()
    if not rings:
        return []

    raised: list[FraudFlag] = []
    for ring in rings:
        members = list(ring.members)

        # The graph is a DERIVED read model and can outlive Postgres: a deleted
        # account leaves its node and edges behind until the projection catches
        # up. Flagging a member who no longer exists violates the foreign key
        # and takes the whole sweep down with it, so confirm every member is a
        # real user first. A ring with missing members is skipped rather than
        # partially flagged - the finding is about the group, and a group we
        # cannot fully identify is not one an admin can act on.
        live = set(
            (
                await db.scalars(
                    select(User.id).where(
                        User.id.in_(members), User.deleted_at.is_(None)
                    )
                )
            ).all()
        )
        if len(live) != len(members):
            logger.info(
                "collusion: skipping a ring with %d member(s) missing from Postgres "
                "- the graph is stale for this cluster",
                len(members) - len(live),
            )
            continue
        # One open flag per member per ring. Re-running the sweep must not
        # stack a fresh accusation on every tick for the same finding.
        signature = "-".join(sorted(str(m)[:8] for m in members))

        # Read what these people actually asked each other for. Structure and
        # money flow are identical for a real friend group and a farming ring;
        # the errand text is the only place they differ. Advisory: it annotates
        # the flag for the admin and never changes what happens automatically.
        verdict = await semantics.assess_cluster(db, members)
        semantic = semantics.verdict_details(verdict)

        for member in members:
            already = await db.scalar(
                select(func.count())
                .select_from(FraudFlag)
                .where(
                    FraudFlag.user_id == member,
                    FraudFlag.rule == "COLLUSION_RING",
                    FraudFlag.status == "OPEN",
                    FraudFlag.details["signature"].astext == signature,
                )
            )
            if already:
                continue

            flag = FraudFlag(
                user_id=member,
                rule="COLLUSION_RING",
                severity=3,
                details={
                    "signature": signature,
                    "members": [str(m) for m in members],
                    "names": list(ring.names),
                    "size": ring.size,
                    "laps": ring.laps,
                    "total_value": round(ring.total_value, 2),
                    "min_leg_value": round(ring.min_leg_value, 2),
                    "closure": round(ring.closure, 3),
                    **semantic,
                },
            )
            db.add(flag)
            raised.append(flag)

    if raised:
        await db.flush()
        logger.info("collusion sweep raised %d flag(s)", len(raised))
    return raised


async def sweep_rating_farming(db: AsyncSession) -> list[FraudFlag]:
    """Find runners whose reputation rests on their own circle, and check it.

    The attack this closes: scam strangers, absorb the price flag and the
    reputation penalty, then run errands for friends and collect five stars
    until ranking offers you strangers again.

    Two-stage on purpose. Arithmetic decides WHO to look at - concentration, a
    friends-versus-strangers gap, and high in-cluster ratings arriving right
    after a penalty. It is cheap, exact, and cannot be gamed by writing well.
    Only then is the language model asked whether those reviews describe
    errands that actually happened, which is the one question arithmetic cannot
    answer and the one that protects a genuinely well-liked runner.

    No punishment is applied here. A concentrated reputation is already
    self-limiting - the weighting in reputation.py shrinks it toward neutral -
    so this raises the case for a human rather than acting twice on one fact.
    """
    since = datetime.now(UTC) - timedelta(days=PATTERN_WINDOW_DAYS)

    # Only runners who were actually rated recently; there is no point
    # profiling an account nobody has used.
    recent = list(
        await db.scalars(
            select(Rating.ratee_id)
            .where(Rating.created_at >= since)
            .group_by(Rating.ratee_id)
            .having(func.count() >= reputation.FARMING_MIN_IN_CLUSTER)
        )
    )
    if not recent:
        return []

    raised: list[FraudFlag] = []
    for runner_id in recent:
        profile = await reputation.recompute(db, runner_id)
        signals = reputation.farming_signals(profile)
        if signals is None:
            continue

        already = await db.scalar(
            select(func.count())
            .select_from(FraudFlag)
            .where(
                FraudFlag.user_id == runner_id,
                FraudFlag.rule == "RATING_FARMING",
                FraudFlag.status == "OPEN",
            )
        )
        if already:
            continue

        # Ask the model only about cases arithmetic already surfaced. Running
        # it over every runner would cost a fortune and, worse, would put a
        # language judgement in front of people nothing was wrong with.
        #
        # Off by default: this channel was measured not to discriminate, and an
        # advisory that clears fraudsters who write well while failing honest
        # runners whose friends write nothing is worse than no advisory at all.
        # See settings.review_analysis_enabled.
        verdict = (
            await semantics.assess_reviews(db, runner_id)
            if settings.review_analysis_enabled
            else None
        )

        flag = FraudFlag(
            user_id=runner_id,
            rule="RATING_FARMING",
            severity=2,
            details={**signals, **semantics.review_details(verdict)},
        )
        db.add(flag)
        raised.append(flag)

    if raised:
        await db.flush()
        logger.info("rating-farming sweep raised %d flag(s)", len(raised))
    return raised


# -------------------------------------------------- reference auto-upkeep


async def refresh_reference(
    db: AsyncSession, campus_id: uuid.UUID, item_key: str
) -> ReferencePrice | None:
    """Re-estimate one item from recent honest claims.

    FLAGGED claims are excluded from the evidence. That exclusion is the whole
    ballgame: feed judged-fraudulent claims back in and the reference climbs to
    meet them, which is the failure this design exists to prevent.
    """
    reference = await get_reference(db, campus_id, item_key)
    since = datetime.now(UTC) - timedelta(days=PATTERN_WINDOW_DAYS)

    # Runners under an open or upheld "walking the line" flag do not get a vote
    # on where the line is. Their claims are legal individually, which is
    # exactly why they would otherwise be the most effective way to drag a
    # reference upward - never tripping a rule while always pushing.
    suspect = select(FraudFlag.user_id).where(
        FraudFlag.rule == "PERSISTENT_NEAR_THRESHOLD",
        FraudFlag.status.in_(("OPEN", "UPHELD")),
    )

    rows = await db.execute(
        select(RunnerPriceClaim.runner_id, RunnerPriceClaim.claimed_unit_price).where(
            RunnerPriceClaim.campus_id == campus_id,
            RunnerPriceClaim.item_key == item_key,
            RunnerPriceClaim.created_at >= since,
            # FLAGGED claims are excluded outright; ELEVATED ones are kept on
            # purpose, because a genuine price rise shows up first as everyone
            # paying a little more, and the reference has to be able to follow.
            RunnerPriceClaim.verdict != "FLAGGED",
            RunnerPriceClaim.runner_id.not_in(suspect),
        )
    )
    by_runner: dict[str, list[Decimal]] = {}
    for runner_id, price in rows:
        by_runner.setdefault(str(runner_id), []).append(_money(price))

    est = estimator.estimate_reference(
        by_runner,
        band_min=_money(reference.band_min) if reference else None,
        band_max=_money(reference.band_max) if reference else None,
    )

    if reference is None:
        # Nothing to update yet - an unpriced item needs an admin to set the
        # band before any estimate is allowed to mean anything.
        return None

    if est.usable and est.value is not None:
        reference.reference_price = est.value
        reference.source = "AUTO"
        reference.sample_count = est.sample_count
        reference.last_estimated_at = datetime.now(UTC)

    if est.needs_proposal and est.observed_median is not None:
        await _propose(db, reference, est)

    await db.flush()
    return reference


async def _propose(
    db: AsyncSession, reference: ReferencePrice, est: estimator.Estimate
) -> ReferencePriceProposal | None:
    """Ask an admin to move the band. One open proposal per item at a time."""
    open_already = await db.scalar(
        select(func.count())
        .select_from(ReferencePriceProposal)
        .where(
            ReferencePriceProposal.reference_price_id == reference.id,
            ReferencePriceProposal.status == "PENDING",
        )
    )
    if open_already:
        return None

    observed = est.observed_median
    assert observed is not None
    band_min, band_max = estimator.propose_band(observed)
    proposal = ReferencePriceProposal(
        reference_price_id=reference.id,
        proposed_price=observed,
        proposed_band_min=band_min,
        proposed_band_max=band_max,
        observed_median=observed,
        sample_count=est.sample_count,
        reason=est.reason,
    )
    db.add(proposal)
    await db.flush()
    return proposal


async def refresh_all_references(db: AsyncSession, campus_id: uuid.UUID) -> int:
    """Sweep every priced item on a campus. Driven by the worker's scheduler."""
    keys = await known_keys(db, campus_id)
    for key in keys:
        await refresh_reference(db, campus_id, key)
    return len(keys)


# ------------------------------------------------------------ admin review


async def review_flag(
    db: AsyncSession,
    redis: Redis,
    *,
    flag: FraudFlag,
    admin: User,
    uphold: bool,
) -> FraudFlag:
    """An admin's verdict on a flag, and the money that follows from it."""
    flag.status = "UPHELD" if uphold else "DISMISSED"
    flag.reviewed_at = datetime.now(UTC)
    flag.reviewed_by = admin.id

    if flag.errand_id:
        errand = await db.get(Errand, flag.errand_id)
        if errand and errand.runner_id:
            try:
                await ledger.resolve_withheld(
                    db,
                    errand_id=errand.id,
                    runner_id=errand.runner_id,
                    pay_runner=not uphold,
                    memo="Admin review of flagged price claim",
                )
            except ledger.LedgerError:
                # Nothing was withheld on this errand (settled clean, or already
                # resolved). The verdict still stands on the flag itself.
                pass

    if not uphold and flag.claim_id:
        # Dismissed: the claim was honest, so let it count as evidence again.
        claim = await db.get(RunnerPriceClaim, flag.claim_id)
        if claim:
            claim.verdict = "OK"

    await db.flush()
    return flag
