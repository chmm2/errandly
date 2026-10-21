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

# Stand-in for an infinite z when the predicted probabilities leave no variance.
Z_DEGENERATE = 99.0


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


# --- a fitted model of who actually accepts ----------------------------------
#
# The scores in the offer log are the ROUTER's preference, and the router does
# not decide who accepts: every runner in a tier is told at the same moment and
# the first to tap wins. Reusing those scores as the behavioural model
# overstated the router's influence badly enough that a ring whose partner made
# sure to be the router's first pick read as fully explained (recall 0.02 in
# simulation). So the model is now FITTED to what runners have actually done:
# a conditional logit over a few logged features, estimated by maximum
# likelihood on rounds posted by people outside the groups under suspicion.

# Rounds with an acceptor among the logged candidates needed before the fitted
# model is trusted. Below this the router's own scores are used, as before.
MIN_CALIBRATION_ROUNDS = 200
RIDGE = 1e-2
_NEWTON_STEPS = 30


def _features(candidate: dict) -> tuple[float, float, float, float]:
    hops = candidate.get("hops")
    return (
        float(candidate.get("distance_m") or 0.0) / 1000.0,
        1.0 if hops == 1 else 0.0,
        1.0 if hops == 2 else 0.0,
        float(candidate.get("reputation") or 3.5) - 3.5,
    )


@dataclass(frozen=True)
class AcceptanceModel:
    """Fitted conditional-logit weights: distance (km), direct friend,
    friend-of-friend, reputation above neutral."""

    coef: tuple[float, float, float, float]
    rounds: int

    def probabilities(self, candidates: list[dict]) -> list[float]:
        if not candidates:
            return []
        utils = [sum(b * x for b, x in zip(self.coef, _features(c))) for c in candidates]
        top = max(utils)
        weights = [math.exp(u - top) for u in utils]
        total = sum(weights)
        return [w / total for w in weights]


def _solve(a: list[list[float]], b: list[float]) -> list[float]:
    """Gaussian elimination with partial pivoting, for a 4x4 system."""
    n = len(b)
    m = [row[:] + [b[i]] for i, row in enumerate(a)]
    for col in range(n):
        piv = max(range(col, n), key=lambda r: abs(m[r][col]))
        m[col], m[piv] = m[piv], m[col]
        if abs(m[col][col]) < 1e-12:
            return [0.0] * n
        for r in range(col + 1, n):
            f = m[r][col] / m[col][col]
            for c in range(col, n + 1):
                m[r][c] -= f * m[col][c]
    x = [0.0] * n
    for r in range(n - 1, -1, -1):
        x[r] = (m[r][n] - sum(m[r][c] * x[c] for c in range(r + 1, n))) / m[r][r]
    return x


def fit_acceptance_model(rows) -> AcceptanceModel | None:
    """Maximum-likelihood conditional logit over logged rounds, or None.

    Only rounds whose acceptor is among the logged candidates carry
    information about choice among them; the rest are skipped.
    """
    data = []
    for row in rows:
        if row.accepted_runner_id is None:
            continue
        cands = row.candidates or []
        if len(cands) < 2:
            continue
        ids = [c.get("runner_id") for c in cands]
        taker = str(row.accepted_runner_id)
        if taker not in ids:
            continue
        data.append(([_features(c) for c in cands], ids.index(taker)))
    if len(data) < MIN_CALIBRATION_ROUNDS:
        return None

    k = 4
    beta = [0.0] * k
    for _ in range(_NEWTON_STEPS):
        grad = [-RIDGE * b for b in beta]
        hess = [[-RIDGE if i == j else 0.0 for j in range(k)] for i in range(k)]
        for xs, y in data:
            utils = [sum(b * x for b, x in zip(beta, f)) for f in xs]
            top = max(utils)
            ws = [math.exp(u - top) for u in utils]
            tot = sum(ws)
            ps = [w / tot for w in ws]
            mean = [sum(p * f[a] for p, f in zip(ps, xs)) for a in range(k)]
            for a in range(k):
                grad[a] += xs[y][a] - mean[a]
                for c in range(k):
                    second = sum(p * f[a] * f[c] for p, f in zip(ps, xs))
                    hess[a][c] -= second - mean[a] * mean[c]
        step = _solve(hess, grad)
        beta = [b - s for b, s in zip(beta, step)]
        if max(abs(s) for s in step) < 1e-7:
            break
    return AcceptanceModel(coef=tuple(beta), rounds=len(data))


async def fit_from_log(
    db: AsyncSession, exclude: set[uuid.UUID] | None = None
) -> AcceptanceModel | None:
    """Fit on the window's rounds, leaving out rounds posted by `exclude`
    (the members of every candidate ring), so a group never calibrates the
    model that judges it."""
    since = datetime.now(UTC) - timedelta(days=WINDOW_DAYS)
    stmt = select(OfferLog).where(OfferLog.created_at >= since)
    if exclude:
        stmt = stmt.where(OfferLog.requester_id.not_in(list(exclude)))
    try:
        rows = list(await db.scalars(stmt))
    except Exception:
        logger.warning("acceptance model: offer log unavailable", exc_info=True)
        return None
    return fit_acceptance_model(rows)


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
    db: AsyncSession, members: list[uuid.UUID], model: AcceptanceModel | None = None
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

        probs = (
            model.probabilities(candidates) if model is not None
            else _acceptance_probabilities(candidates)
        )
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

    if variance > 1e-9:
        z = (observed - expected) / math.sqrt(variance)
    elif abs(observed - expected) < 0.5:
        # Every round was a foregone conclusion and the outcome matched it.
        z = 0.0
    else:
        # Every round was a foregone conclusion and the group beat it anyway:
        # as unexplained as it gets. Reported as a large finite value so the
        # flag's details stay valid JSON.
        z = math.copysign(Z_DEGENERATE, observed - expected)
    return PolicyExcess(
        rounds=counted,
        observed=observed,
        expected=expected,
        z=z,
        explored_rounds=explored,
    )
