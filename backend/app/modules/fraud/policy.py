"""Did the routing policy already explain this group's in-group activity?

`collusion.py` finds a closed money cycle among mutual friends. That shape is
strong evidence — but it is also exactly what the matcher produces on its own,
because matching deliberately offers errands to friends first. A closed friend
group that never colludes still circulates money, and the harder the social
boost is turned up, the more of it they circulate. The detector and the matcher
therefore disagree about what a cycle means, and the detector has no way to
tell whose doing it was.

This module supplies the missing comparison. The offer log records, for every
dispatch round, the candidate set and each candidate's score. From those scores
the policy's own preference is recoverable: how likely was it, at that moment,
that this errand went to somebody inside the group? Summing that across rounds
gives what the policy EXPECTED. Comparing it against what actually happened
gives the part the policy cannot explain — which is the only part that is
evidence about the people rather than about the router.

    excess  =  observed in-group takes  −  expected in-group takes

Expressed as a standardised deviation this is a test statistic rather than a
tuned constant, so the question "how surprising is this?" finally has a number
attached to it.

Two design rules, both inherited from the rest of the fraud module:

1. **Silence is not innocence and not guilt.** With too few logged rounds this
   returns None and the caller behaves exactly as it did before. A detector
   that quietly changes verdict because an analytics table is thin would be
   worse than one that never consulted it.

2. **It can only ever exculpate.** A low excess suppresses a flag; a high
   excess never raises severity or manufactures one. The cycle evidence still
   has to stand on its own first. Being wrong in the exculpatory direction
   costs a missed ring; being wrong the other way accuses a real student.
"""

from __future__ import annotations

import logging
import math
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.errands.models import OfferLog

logger = logging.getLogger(__name__)

# How sharply a difference in score translates into a difference in the chance
# of being the one who accepts. Offers go to every candidate at once and the
# first to tap wins, so this is a soft preference rather than a hard pick: the
# top-ranked runner usually accepts, but not always. 300 m is the scale over
# which that advantage becomes decisive.
TAU_M = 300.0

# Below this many logged rounds the estimate is noise. A group with three
# errands between them cannot support a claim about what the policy expected.
MIN_ROUNDS = 25

# How far back to read. Matches the collusion money window so the two halves of
# the evidence describe the same period.
WINDOW_DAYS = 180

# Standardised deviations before in-group activity counts as unexplained.
# 3.0 is roughly a one-in-a-thousand coincidence.
Z_UNEXPLAINED = 3.0


@dataclass(frozen=True)
class PolicyExcess:
    """What the policy expected of a group, against what it actually got."""

    rounds: int
    observed: int          # rounds an in-group runner accepted
    expected: float        # rounds the policy predicted one would
    z: float               # standardised excess
    explored_rounds: int   # socially-blind rounds inside the sample

    @property
    def observed_share(self) -> float:
        return self.observed / self.rounds if self.rounds else 0.0

    @property
    def expected_share(self) -> float:
        return self.expected / self.rounds if self.rounds else 0.0

    @property
    def explained(self) -> bool:
        """True when the routing policy accounts for what was observed."""
        return self.z < Z_UNEXPLAINED

    def as_details(self) -> dict:
        return {
            "rounds": self.rounds,
            "explored_rounds": self.explored_rounds,
            "observed_share": round(self.observed_share, 3),
            "expected_share": round(self.expected_share, 3),
            "excess_share": round(self.observed_share - self.expected_share, 3),
            "z": round(self.z, 2),
            "explained_by_policy": self.explained,
        }


def _acceptance_probabilities(candidates: list[dict]) -> list[float]:
    """Turn the logged scores into the policy's own preference over candidates.

    A softmax over negated effective distance. The scores are already in metres
    and already carry whichever terms were applied on that round — including
    the absence of the social term on an exploring round — so nothing has to be
    re-derived from a graph that has since moved on.
    """
    scores = [float(c.get("effective", 0.0)) for c in candidates]
    if not scores:
        return []
    best = min(scores)
    weights = [math.exp(-(s - best) / TAU_M) for s in scores]
    total = sum(weights)
    if total <= 0:
        n = len(weights)
        return [1.0 / n] * n
    return [w / total for w in weights]


async def excess_for_group(
    db: AsyncSession, members: list[uuid.UUID]
) -> PolicyExcess | None:
    """How much of this group's in-group activity the policy cannot explain.

    Returns None when there is not enough logged history to say anything, which
    is the state every deployment starts in.
    """
    if len(members) < 2:
        return None

    member_ids = {str(m) for m in members}
    since = datetime.now(UTC) - timedelta(days=WINDOW_DAYS)

    rows = list(
        await db.scalars(
            select(OfferLog).where(
                OfferLog.requester_id.in_(members),
                OfferLog.created_at >= since,
            )
        )
    )

    observed = 0
    expected = 0.0
    variance = 0.0
    counted = 0
    explored = 0

    for row in rows:
        # A round nobody accepted says nothing about who was chosen.
        if row.accepted_runner_id is None:
            continue
        candidates = row.candidates or []
        if len(candidates) < 2:
            # With one candidate the policy had no choice to express, so the
            # outcome carries no information about preference.
            continue

        probs = _acceptance_probabilities(candidates)
        p_in = sum(
            p for c, p in zip(candidates, probs)
            if c.get("runner_id") in member_ids
            and c.get("runner_id") != str(row.requester_id)
        )
        # Poisson-binomial: each round is its own Bernoulli trial with its own
        # probability, so variances add rather than sharing a single p.
        expected += p_in
        variance += p_in * (1.0 - p_in)
        counted += 1
        if row.exploring:
            explored += 1
        if str(row.accepted_runner_id) in member_ids:
            observed += 1

    if counted < MIN_ROUNDS:
        logger.debug(
            "policy excess: only %d usable rounds for this group, need %d",
            counted, MIN_ROUNDS,
        )
        return None

    z = (observed - expected) / math.sqrt(variance) if variance > 1e-9 else 0.0
    return PolicyExcess(
        rounds=counted,
        observed=observed,
        expected=expected,
        z=z,
        explored_rounds=explored,
    )
