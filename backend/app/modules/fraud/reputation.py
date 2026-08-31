"""Rating provenance: who vouched for this runner, and does it mean anything.

A star rating is only as good as its independence. The attack this module
exists to stop runs in two moves:

    1. Scam strangers. Take the price flag and the reputation penalty.
    2. Run errands for your own friends, collect five stars, and float the
       score back up until matching offers you strangers again.

Every individual rating in step 2 may be sincere. That is what makes it hard,
and it is why the answer here is **weighting rather than forbidding**. Friends
genuinely do run errands for each other and genuinely do rate each other well;
a platform that discounted every friend's rating would punish the honest
majority to inconvenience a few.

So the discount is not applied to friendship. It is applied to
**concentration** — how much of a runner's reputation rests on their own
cluster. Rated well by twenty strangers and five friends? Nothing changes.
Rated only by your own circle? The score does not become *low*; it becomes
*low-confidence*, and matching treats an unproven runner as unproven rather
than as bad. Recovering a penalised score then requires strangers, which is
precisely the behaviour the platform wants back.

Friendship is read from Postgres, not the graph, so all of this keeps working
when Neo4j is down. Reputation is too important to depend on a read model.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.models import User
from app.modules.errands.models import Rating
from app.modules.fraud.models import UserStrike
from app.modules.social.models import Friendship

logger = logging.getLogger(__name__)

# Below this share of in-cluster ratings, nothing is discounted at all. Most
# runners will have friends among their customers and that is not a finding.
CONCENTRATION_KNEE = 0.50

# The most a friend's rating can be discounted, at total concentration. Never
# 1.0: a real errand was really delivered, and erasing the rating entirely
# would punish the runner for who their customers happened to be.
MAX_RATING_DISCOUNT = 0.75

# Ratings-worth of prior pulling an unproven runner toward the neutral middle.
# A runner with two ratings should not outrank one with fifty on a lucky start.
CONFIDENCE_PRIOR = 8.0
NEUTRAL_RATING = 3.5

# --- farming detection ------------------------------------------------------

# All three gates must hold before anything is raised.
FARMING_MIN_IN_CLUSTER = 4
FARMING_CONCENTRATION = 0.70
# How much better friends rate them than strangers do, in stars.
FARMING_DIFFERENTIAL = 0.8
FARMING_MIN_OUT_CLUSTER = 3
# In-cluster ratings arriving right after a penalty. Timing is the hardest
# signal to explain away, so it stands on its own.
POST_PENALTY_DAYS = 14
POST_PENALTY_BURST = 2

# The third route, for the farmer the first two cannot see.
#
# The differential needs strangers to compare against; the burst needs a prior
# penalty. Someone who farms reputation from a standing start - never caught,
# never served a stranger - trips neither, and can build standing purely inside
# their circle before ever meeting a victim. That is the ordering an unhurried
# attacker would choose.
#
# What gives them away is accumulation without independence: a substantial
# rating history in which nobody outside their circle has ever rated them, and
# in which a few friends rate repeatedly. Set high enough that an ordinary new
# runner whose first customers were friends is nowhere near it - they have
# four or five ratings, not fifteen.
UNPROVEN_MIN_IN_CLUSTER = 15
UNPROVEN_MAX_OUT_CLUSTER = 1
# Ratings per distinct friend. At 2.5, fifteen ratings come from six people or
# fewer, which is a circle rather than a customer base.
UNPROVEN_REPEAT_RATIO = 2.5


@dataclass(frozen=True)
class RatingProfile:
    """Where a runner's reputation actually comes from.

    `in_cluster`/`out_cluster` count RATINGS, and are what the admin console
    reports because "9 of 12 ratings came from friends" is what a reviewer
    wants to read. `in_raters`/`out_raters` count PEOPLE, and are what the
    weighting uses - see build_profile for why the difference matters.
    """

    in_cluster: int = 0
    out_cluster: int = 0
    in_raters: int = 0
    out_raters: int = 0
    mean_in: float | None = None
    mean_out: float | None = None
    post_penalty_in_cluster: int = 0
    weighted_score: float = NEUTRAL_RATING
    weight_total: float = 0.0

    @property
    def total(self) -> int:
        return self.in_cluster + self.out_cluster

    @property
    def distinct_raters(self) -> int:
        return self.in_raters + self.out_raters

    @property
    def repeat_ratio(self) -> float:
        """Ratings per distinct rater. A handful of friends rating over and
        over reads very differently from the same count spread across a
        cohort, and only the first is cheap to manufacture."""
        return self.total / self.distinct_raters if self.distinct_raters else 0.0

    @property
    def concentration(self) -> float:
        return self.in_cluster / self.total if self.total else 0.0

    @property
    def differential(self) -> float | None:
        if self.mean_in is None or self.mean_out is None:
            return None
        return self.mean_in - self.mean_out

    @property
    def confidence(self) -> float:
        """How much this score should be believed, in [0, 1).

        Effective sample size against a prior, so a runner carried entirely by
        their own cluster is treated as unproven rather than as good. The
        sample counts PEOPLE, not ratings: twenty ratings from five friends is
        five opinions, and treating it as twenty is what let volume defeat the
        discount (see build_profile).
        """
        return self.weight_total / (self.weight_total + CONFIDENCE_PRIOR)

    @property
    def matching_score(self) -> float:
        """Reputation shrunk toward neutral by confidence. What ranking reads."""
        c = self.confidence
        return c * self.weighted_score + (1 - c) * NEUTRAL_RATING


def rating_weight(concentration: float, rater_is_friend: bool) -> float:
    """How much one rating counts toward reputation.

    A stranger's rating always counts fully. A friend's is discounted only in
    proportion to how far past the knee the runner's concentration sits — so
    the discount tracks the *shape of the evidence*, never the friendship
    itself.
    """
    if not rater_is_friend or concentration <= CONCENTRATION_KNEE:
        return 1.0
    excess = (concentration - CONCENTRATION_KNEE) / (1.0 - CONCENTRATION_KNEE)
    return 1.0 - min(MAX_RATING_DISCOUNT, excess * MAX_RATING_DISCOUNT)


async def _friend_ids(db: AsyncSession, user_id: uuid.UUID) -> set[uuid.UUID]:
    rows = await db.scalars(
        select(Friendship).where(
            Friendship.status == "ACCEPTED",
            or_(Friendship.user_lo == user_id, Friendship.user_hi == user_id),
        )
    )
    return {r.user_hi if r.user_lo == user_id else r.user_lo for r in rows}


async def build_profile(db: AsyncSession, runner_id: uuid.UUID) -> RatingProfile:
    """Split a runner's ratings by whether the rater is one of their friends."""
    ratings = list(
        await db.scalars(select(Rating).where(Rating.ratee_id == runner_id))
    )
    if not ratings:
        return RatingProfile()

    friends = await _friend_ids(db, runner_id)
    inside = [r for r in ratings if r.rater_id in friends]
    outside = [r for r in ratings if r.rater_id not in friends]

    def mean(rs: list[Rating]) -> float | None:
        return round(sum(r.stars for r in rs) / len(rs), 3) if rs else None

    total = len(ratings)
    concentration = len(inside) / total if total else 0.0

    # ONE RATER, ONE VOTE.
    #
    # Weight is accumulated per PERSON, not per rating: each rater contributes
    # a single vote carrying their own mean. Without this the discount is
    # defeated by patience - a friend rating still carries 0.25 after the
    # maximum discount, so weight grew without bound and roughly a hundred
    # farmed ratings overtook twenty honest ones. Measured before this change:
    # 100 in-cluster ratings scored 4.64 against 4.57 for 20 stranger ratings.
    #
    # Counting people instead removes the exploit at its root rather than
    # tuning the cap, and it is the same rule the price estimator and the
    # store adjustment already use. It also costs an honest frequent customer
    # nothing that is real: twenty ratings from one person genuinely is one
    # person's opinion.
    #
    # The weight itself still depends on concentration, which depends on the
    # whole set, so it is computed once here rather than per rating.
    by_rater: dict[uuid.UUID, list[float]] = {}
    for r in ratings:
        by_rater.setdefault(r.rater_id, []).append(float(r.stars))

    weighted_sum = 0.0
    weight_total = 0.0
    for rater_id, stars in by_rater.items():
        vote = sum(stars) / len(stars)
        w = rating_weight(concentration, rater_id in friends)
        weighted_sum += w * vote
        weight_total += w

    last_penalty = await db.scalar(
        select(func.max(UserStrike.created_at)).where(
            UserStrike.user_id == runner_id,
            UserStrike.action.in_(("REPUTATION_PENALTY", "WARNING")),
        )
    )
    burst = 0
    if last_penalty is not None:
        window_end = last_penalty + timedelta(days=POST_PENALTY_DAYS)
        burst = sum(
            1
            for r in inside
            if last_penalty <= r.created_at <= window_end and r.stars >= 4
        )

    return RatingProfile(
        in_cluster=len(inside),
        out_cluster=len(outside),
        in_raters=len({r.rater_id for r in inside}),
        out_raters=len({r.rater_id for r in outside}),
        mean_in=mean(inside),
        mean_out=mean(outside),
        post_penalty_in_cluster=burst,
        weighted_score=round(weighted_sum / weight_total, 3) if weight_total else NEUTRAL_RATING,
        weight_total=round(weight_total, 3),
    )


def farming_signals(profile: RatingProfile) -> dict | None:
    """Whether this rating profile looks farmed, and on which evidence.

    Returns None unless a gate actually trips. Two independent routes, because
    they catch different attackers: a *differential* (friends rate them far
    better than strangers do) and a *burst* (in-cluster praise arriving right
    after a penalty). The second needs no strangers at all, which matters —
    the runner who has stopped getting stranger work is exactly the one
    farming.
    """
    if profile.in_cluster < FARMING_MIN_IN_CLUSTER:
        return None
    if profile.concentration < FARMING_CONCENTRATION:
        return None

    reasons: list[str] = []

    diff = profile.differential
    if (
        diff is not None
        and profile.out_cluster >= FARMING_MIN_OUT_CLUSTER
        and diff >= FARMING_DIFFERENTIAL
    ):
        reasons.append(
            f"friends rate them {diff:.1f} stars higher than strangers do "
            f"({profile.mean_in:.1f} vs {profile.mean_out:.1f})"
        )

    if profile.post_penalty_in_cluster >= POST_PENALTY_BURST:
        reasons.append(
            f"{profile.post_penalty_in_cluster} high ratings from inside their own "
            f"circle within {POST_PENALTY_DAYS} days of a penalty"
        )

    # Standing built entirely inside the circle, with nobody outside it ever
    # having rated them, and a few friends rating over and over.
    if (
        profile.in_cluster >= UNPROVEN_MIN_IN_CLUSTER
        and profile.out_cluster <= UNPROVEN_MAX_OUT_CLUSTER
        and profile.repeat_ratio >= UNPROVEN_REPEAT_RATIO
    ):
        reasons.append(
            f"{profile.in_cluster} ratings from only {profile.in_raters} friends and "
            f"{profile.out_cluster} from anyone else - a reputation no stranger has "
            "ever tested"
        )

    if not reasons:
        return None

    return {
        "concentration": round(profile.concentration, 2),
        "in_cluster": profile.in_cluster,
        "out_cluster": profile.out_cluster,
        "mean_in": profile.mean_in,
        "mean_out": profile.mean_out,
        "differential": round(diff, 2) if diff is not None else None,
        "post_penalty_burst": profile.post_penalty_in_cluster,
        "reasons": reasons,
    }


async def recompute(db: AsyncSession, runner_id: uuid.UUID) -> RatingProfile:
    """Refresh the stored weighted score so matching can read it cheaply.

    `reputation_score` keeps its plain meaning — the raw average a person sees
    on their profile. `effective_reputation` is the provenance-weighted figure
    ranking uses. Keeping them separate matters: showing someone a discounted
    number on their own profile, with no explanation, would be worse than not
    discounting at all.
    """
    profile = await build_profile(db, runner_id)
    user = await db.get(User, runner_id)
    if user is not None:
        user.effective_reputation = round(profile.matching_score, 2)
        user.rating_confidence = round(profile.confidence, 3)
    return profile
