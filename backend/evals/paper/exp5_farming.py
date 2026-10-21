"""Experiment 5: reputation farming with authentic ratings.

A runner's ratings are built under several attack strategies and passed
through the production fraud.reputation.build_profile (rating split by
provenance, one-rater-one-vote weighting, confidence shrinkage) and
farming_signals (differential, post-penalty burst, unproven accumulation).

Two comparison weightings are computed from the same ratings:
  raw_mean    the plain average a student sees on a profile
  per_rating  the weighting before it was moved to one vote per rater: each
              rating weighted by rating_weight(), so volume accumulates weight

Run: python -m evals.paper.exp5_farming
"""

from __future__ import annotations

import asyncio
import random
import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from app.modules.errands.service import NEUTRAL_REPUTATION, REPUTATION_WEIGHT_M
from app.modules.fraud import reputation
from evals.paper.common import save

RUNNER = uuid.UUID(int=1)
T0 = datetime.now(UTC) - timedelta(days=60)


class _ProfileSession:
    """Stands in for AsyncSession in build_profile: ratings, friendships, last strike."""

    def __init__(self, ratings, friend_ids, last_strike):
        self._answers = [ratings, [
            SimpleNamespace(user_lo=min(RUNNER, f), user_hi=max(RUNNER, f), status="ACCEPTED")
            for f in friend_ids
        ]]
        self._strike = last_strike

    async def scalars(self, _stmt):
        return iter(self._answers.pop(0))

    async def scalar(self, _stmt):
        return self._strike


def rating(rater, stars, day):
    return SimpleNamespace(rater_id=rater, ratee_id=RUNNER, stars=stars,
                           created_at=T0 + timedelta(days=day))


def person(i: int) -> uuid.UUID:
    return uuid.UUID(int=1000 + i)


def per_rating_score(ratings, friends):
    conc = sum(1 for r in ratings if r.rater_id in friends) / len(ratings) if ratings else 0
    w = [reputation.rating_weight(conc, r.rater_id in friends) for r in ratings]
    wt = sum(w)
    score = sum(wi * r.stars for wi, r in zip(w, ratings)) / wt if wt else NEUTRAL_REPUTATION
    c = wt / (wt + reputation.CONFIDENCE_PRIOR)
    return c * score + (1 - c) * NEUTRAL_REPUTATION


async def profile(ratings, friends, strike_day=None):
    strike = T0 + timedelta(days=strike_day) if strike_day is not None else None
    p = await reputation.build_profile(_ProfileSession(ratings, friends, strike), RUNNER)
    sig = reputation.farming_signals(p)
    raw = sum(r.stars for r in ratings) / len(ratings) if ratings else NEUTRAL_REPUTATION
    return {
        "ratings": len(ratings),
        "raw_mean": round(raw, 3),
        "per_rating": round(per_rating_score(ratings, friends), 3),
        "production": round(p.matching_score, 3),
        "confidence": round(p.confidence, 3),
        "rank_offset_m": round((p.matching_score - NEUTRAL_REPUTATION) * REPUTATION_WEIGHT_M, 0),
        "flagged": sig is not None,
        "reasons": [] if sig is None else [r.split(" ")[0:6] for r in sig["reasons"]],
        "signals": None if sig is None else {
            "differential": sig["differential"], "burst": sig["post_penalty_burst"],
            "concentration": sig["concentration"]},
    }


async def main() -> dict:
    rng = random.Random(11)
    out = {}

    # The benchmark everyone is compared against: twenty strangers who were
    # mostly happy, and five friends who were very happy.
    strangers = [person(i) for i in range(20)]
    friends5 = {person(100 + i) for i in range(5)}
    honest = [rating(s, rng.choice((4, 5, 5, 5, 5)), rng.uniform(0, 50)) for s in strangers]
    honest += [rating(f, 5, rng.uniform(0, 50)) for f in friends5]
    out["honest_broad"] = await profile(honest, friends5)

    honest20 = [rating(s, 5, rng.uniform(0, 50)) for s in strangers]
    out["honest_20_strangers_all_five"] = await profile(honest20, set())

    volumes = (0, 5, 10, 20, 40, 80, 160, 300)

    # A penalised runner: poor service to six strangers, a penalty on day 10,
    # then five-star ratings from m friends, all after the penalty.
    for m in (3, 8):
        rows = []
        friends = {person(200 + i) for i in range(m)}
        flist = sorted(friends)
        for n in volumes:
            rs = [rating(person(300 + i), rng.choice((2, 3, 3, 4)), rng.uniform(0, 9))
                  for i in range(6)]
            rs += [rating(flist[i % m], 5, 10 + rng.uniform(0, 40)) for i in range(n)]
            rows.append({"farmed": n, **await profile(rs, friends, strike_day=10)})
        out[f"penalised_{m}_friends"] = rows

    # Farming from a standing start: never penalised, never served a stranger.
    for m in (3, 8):
        rows = []
        friends = {person(400 + i) for i in range(m)}
        flist = sorted(friends)
        for n in volumes:
            rs = [rating(flist[i % m], 5, rng.uniform(0, 50)) for i in range(n)]
            rows.append({"farmed": n, **await profile(rs, friends)})
        out[f"standing_start_{m}_friends"] = rows

    # Breadth: every farmed rating from a different friend, once each.
    rows = []
    for n in volumes:
        friends = {person(1000 + i) for i in range(n)}
        rs = [rating(f, 5, rng.uniform(0, 50)) for f in sorted(friends)]
        rows.append({"farmed": n, **await profile(rs, friends)})
    out["breadth"] = rows

    for k, v in out.items():
        print(k, v if isinstance(v, dict) else [(r["farmed"], r["raw_mean"], r["per_rating"],
                                                  r["production"], r["flagged"]) for r in v])
    save("exp5_farming", out)
    return out


if __name__ == "__main__":
    asyncio.run(main())
