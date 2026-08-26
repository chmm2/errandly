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

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from redis.asyncio import Redis
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.models import User
from app.modules.errands.models import Errand
from app.modules.fraud import estimator
from app.modules.fraud.models import (
    STRIKE_ACTIONS,
    FraudFlag,
    ReferencePrice,
    ReferencePriceProposal,
    RunnerPriceClaim,
    UserStrike,
)
from app.modules.fraud.normalize import resolve_key
from app.modules.ledger import service as ledger
from app.modules.notifications import service as notifications
from app.modules.runners.models import RunnerProfile

TWO_PLACES = Decimal("0.01")

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

# Claim-vs-reference overshoot bands -> flag severity.
SEVERITY_BANDS = ((Decimal("25"), 1), (Decimal("50"), 2))


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


async def get_reference(
    db: AsyncSession, campus_id: uuid.UUID, item_key: str
) -> ReferencePrice | None:
    return await db.scalar(
        select(ReferencePrice).where(
            ReferencePrice.campus_id == campus_id, ReferencePrice.item_key == item_key
        )
    )


def judge(
    claimed_unit_price: Decimal, quantity: int, reference: ReferencePrice | None
) -> tuple[str, Decimal | None, Decimal]:
    """Return (verdict, delta_pct, eligible_amount) for one claimed line.

    With no reference we cannot call anything fraud - an unpriced item is our
    gap, not the runner's. The claim is paid and becomes evidence toward the
    reference that will judge the next one.
    """
    claimed_unit_price = _money(claimed_unit_price)
    claimed_total = _money(claimed_unit_price * quantity)

    if reference is None:
        return "NO_REFERENCE", None, claimed_total

    ref_unit = _money(reference.reference_price)
    if ref_unit <= 0:
        return "NO_REFERENCE", None, claimed_total

    delta_pct = ((claimed_unit_price - ref_unit) / ref_unit * 100).quantize(TWO_PLACES)
    if delta_pct <= _money(reference.tolerance_pct):
        return "OK", delta_pct, claimed_total

    # Flagged: reimburse what the item is known to cost, withhold the excess.
    # Refusing to pay an unproven excess is not a punishment - it is simply not
    # paying for something nobody can show was spent.
    return "FLAGGED", delta_pct, _money(ref_unit * quantity)


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
    claims: list[RunnerPriceClaim] = []

    for raw_name, unit_price, quantity in lines:
        item_key, _matched = resolve_key(raw_name, keys)
        if not item_key:
            raise FraudError(f"Could not read an item name from '{raw_name}'.", 422)

        reference = await get_reference(db, errand.campus_id, item_key)
        verdict, delta_pct, eligible = judge(unit_price, quantity, reference)

        existing = await db.scalar(
            select(RunnerPriceClaim).where(
                RunnerPriceClaim.errand_id == errand.id,
                RunnerPriceClaim.item_key == item_key,
            )
        )
        if existing is None:
            claim = RunnerPriceClaim(
                errand_id=errand.id,
                runner_id=runner.id,
                campus_id=errand.campus_id,
                raw_name=raw_name[:120],
                item_key=item_key,
                claimed_unit_price=_money(unit_price),
                quantity=quantity,
                reference_snapshot=_money(reference.reference_price) if reference else None,
                delta_pct=delta_pct,
                verdict=verdict,
                eligible_amount=eligible,
            )
            db.add(claim)
        else:
            claim = existing
            claim.raw_name = raw_name[:120]
            claim.claimed_unit_price = _money(unit_price)
            claim.quantity = quantity
            claim.reference_snapshot = _money(reference.reference_price) if reference else None
            claim.delta_pct = delta_pct
            claim.verdict = verdict
            claim.eligible_amount = eligible

        await db.flush()
        claims.append(claim)

        if verdict == "FLAGGED":
            await raise_flag(
                db,
                user_id=runner.id,
                errand_id=errand.id,
                claim=claim,
                rule="CLAIM_ABOVE_REFERENCE",
                delta_pct=delta_pct or Decimal("0"),
            )

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
            "reference": float(claim.reference_snapshot)
            if claim and claim.reference_snapshot
            else None,
            "delta_pct": float(delta_pct),
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

    rows = await db.execute(
        select(RunnerPriceClaim.runner_id, RunnerPriceClaim.claimed_unit_price).where(
            RunnerPriceClaim.campus_id == campus_id,
            RunnerPriceClaim.item_key == item_key,
            RunnerPriceClaim.created_at >= since,
            RunnerPriceClaim.verdict != "FLAGGED",
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
