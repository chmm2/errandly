"""What an *unreviewed* fraud flag is allowed to do to dispatch.

The rest of the fraud stack already reaches matching at both ends of the
ladder. An adjudicated `RUNNER_SUSPENDED` strike sets `fraud_blocked_until`,
drops the runner from the Redis geo set, and `runners/service.py` refuses to
let them come back until it lapses. A `REPUTATION_PENALTY` lowers
`effective_reputation`, which `_rank_with_scores` already reads.

The middle was empty. A flag raised by a sweep — a collusion ring, a run of
rating farming — sat OPEN in the admin console and changed nothing at all: the
runner kept being offered work at full rank until a human found the time to
click. `sweep_collusion_rings` says in its own docstring that it "gates
matching and asks a human". This module is the gating half; until now only the
asking existed.

Two mechanisms, and the difference between them is the whole design:

1. **A demotion, for everyone flagged.** A fourth term in the ranking formula,
   in metres like the other three, so its weight against distance, friendship
   and reputation can be read off rather than inferred. A flagged runner is
   offered less work. They are never removed from the candidate set — an open
   flag is a suspicion nobody has checked yet, and suspending someone on one is
   a punishment the strike ladder deliberately reserves for a human.

2. **One narrow refusal to re-pair.** An errand is not offered to a runner who
   shares an open `COLLUSION_RING` flag with *this requester*. That is not a
   judgement about either person — they both keep taking work from everyone
   else on campus, at a rank cost and no more. It only declines to keep feeding
   the specific dyad whose money the cycle search found going round in a
   circle. A ring needs its own members to transact with each other; this makes
   the platform stop arranging that particular introduction while a human
   looks. The same restraint as flagging every member and naming no ringleader:
   act on the shape that was actually observed, invent nothing beyond it.

**OPEN flags only.** UPHELD ones are excluded deliberately. Once a human
upholds a flag it feeds `evaluate_pattern`, and the strike ladder is then the
sanctioned instrument — it already lowers reputation, which already lowers
rank. Counting the flag here as well would punish one finding twice through two
different mechanisms, and make the total impossible to explain to the person it
lands on. DISMISSED flags are, obviously, gone.

**Absence is neither innocence nor guilt.** Same rule as the language channels
and as `_safe_scores`: if this lookup cannot answer, the caller gets `None` and
dispatch behaves exactly as it did before this module existed. A database
hiccup must never be able to demote or exclude anybody.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.fraud.models import FraudFlag
from app.modules.fraud.service import PATTERN_WINDOW_DAYS

logger = logging.getLogger(__name__)

# What one open flag costs a runner in effective metres, by severity.
#
# Scaled against the terms already in the formula, which is the only way these
# numbers mean anything: SOCIAL_WEIGHT_M is 1500 for a direct friend and
# REPUTATION_WEIGHT_M is 800 per star. A severity-3 flag at 1200 is therefore
# worth less than one friendship and about a star and a half — enough that a
# flagged runner loses most contested match-ups, not so much that they stop
# being offered work. A flagged runner standing at the door still beats a clean
# runner a kilometre away, which is the intended result: this is a thumb on the
# scale, not a suspension.
SEVERITY_WEIGHT_M = {1: 300.0, 2: 700.0, 3: 1200.0}

# The most that unreviewed suspicion may cost, however many flags are open.
#
# Without a cap, flags would simply add up until the penalty exceeded any
# plausible distance and the demotion became a de-facto ban — the hard filter
# this design rejected, arrived at by accumulation instead of by decision. The
# cap is what keeps the sentence bounded: an open flag can cost you at most
# ~2km of queue position, and only a human can do more than that.
INTEGRITY_CAP_M = 2000.0


def decay(age_days: float) -> float:
    """How much a flag still counts, given how long it has gone unreviewed.

    Linear to zero across the same 30-day window the strike ladder counts over
    (`count_recent_flags`), so a runner's standing here and their position on
    the ladder age out together rather than disagreeing about how old is old.

    That unreviewed evidence expires at all is a real concession, and it is the
    existing system's stance rather than a new one: a flag nobody looked at for
    a month is weak evidence, and letting it press on someone's livelihood
    forever — with no human ever having agreed it was true — is the worse
    failure of the two.
    """
    return max(0.0, 1.0 - age_days / PATTERN_WINDOW_DAYS)


async def penalties(
    db: AsyncSession, runner_ids: list[uuid.UUID]
) -> dict[uuid.UUID, float] | None:
    """Effective-metre penalty per candidate, or None if the lookup failed.

    None and {} differ, exactly as they do in `_safe_scores`: {} means "asked,
    nobody here is flagged", None means "no answer". Only the former is a fact
    about anyone.
    """
    if not runner_ids:
        return {}

    since = datetime.now(UTC) - timedelta(days=PATTERN_WINDOW_DAYS)
    try:
        rows = await db.execute(
            select(FraudFlag.user_id, FraudFlag.severity, FraudFlag.created_at).where(
                FraudFlag.user_id.in_(runner_ids),
                FraudFlag.status == "OPEN",
                FraudFlag.created_at >= since,
            )
        )
    except Exception:
        # Deliberately swallowed, and worth being clear about what that does
        # and does not buy. It stops a flag-table problem from deciding
        # anyone's standing, which is the point. It does not rescue the
        # request: this runs inside the caller's transaction, so a genuine
        # connection failure has already poisoned it and will surface at
        # commit. That is the right order — the error still gets reported,
        # it just does not get to demote somebody on its way out.
        logger.warning("integrity standing unavailable", exc_info=True)
        return None

    now = datetime.now(UTC)
    totals: dict[uuid.UUID, float] = {}
    for user_id, severity, created_at in rows:
        weight = SEVERITY_WEIGHT_M.get(severity)
        if weight is None:
            # Severity is a 1-3 DB CHECK, so this is unreachable short of a
            # schema change. Skip rather than guess a weight for a band whose
            # meaning nobody has decided yet.
            logger.warning("integrity: unknown flag severity %r, ignoring", severity)
            continue
        age_days = (now - created_at).total_seconds() / 86400.0
        totals[user_id] = totals.get(user_id, 0.0) + weight * decay(age_days)

    return {uid: min(total, INTEGRITY_CAP_M) for uid, total in totals.items()}


async def co_ringed_with(
    db: AsyncSession, requester_id: uuid.UUID, runner_ids: list[uuid.UUID]
) -> set[uuid.UUID] | None:
    """Candidates sharing an open collusion ring with this requester.

    Reads the requester's own flags: the sweep raises one per member carrying
    the whole `members` list, so a single indexed lookup on the requester
    yields everyone they were found circling money with.

    Returns None when the lookup fails — the caller must then exclude nobody.
    """
    if not runner_ids:
        return set()

    try:
        rows = await db.scalars(
            select(FraudFlag.details).where(
                FraudFlag.user_id == requester_id,
                FraudFlag.rule == "COLLUSION_RING",
                FraudFlag.status == "OPEN",
            )
        )
        details = list(rows)
    except Exception:
        logger.warning("collusion co-membership unavailable", exc_info=True)
        return None

    members: set[uuid.UUID] = set()
    for detail in details:
        for raw in (detail or {}).get("members", []):
            try:
                members.add(uuid.UUID(str(raw)))
            except (ValueError, AttributeError, TypeError):
                # Details is free-form JSONB. A member id that will not parse
                # is a corrupt flag, not a licence to drop the whole finding.
                logger.warning("integrity: unparseable ring member %r", raw)

    # The requester is in their own ring by construction; they are never their
    # own candidate, but discarding them keeps the return value honest.
    members.discard(requester_id)
    return members.intersection(runner_ids)
