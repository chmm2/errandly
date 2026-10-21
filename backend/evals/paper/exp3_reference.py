"""Experiment 3: reference prices under adversarial claims.

One unpriced canteen item (Chicken Puff, admin reference 20, band 15-30, the
seed values). Honest runners report what they paid; a fraction of runners
inflate. The reference is re-estimated weekly from the last 30 days of claims,
and each claim is judged against the reference in force when it was made.

Estimators compared:
  mean_all        mean of every claim in the window
  mean_unflagged  mean of claims not judged FLAGGED
  median_pooled   median of unflagged claims, one vote per claim
  robust          production estimate_reference (one vote per runner, MAD
                  rejection), FLAGGED claims excluded, no band, every runner votes
  robust_excl     robust, and runners under an open PERSISTENT_NEAR_THRESHOLD
                  flag denied a vote (as refresh_reference does)
  robust_band     robust, inside the admin band
  production      both: what refresh_reference actually runs

Judging (judge, effective_tolerance) and the walking-the-line rule
(evaluate_near_threshold) are the production functions.

Run: python -m evals.paper.exp3_reference
"""

from __future__ import annotations

import asyncio
import math
import random
import uuid
from decimal import Decimal
from statistics import mean, median
from types import SimpleNamespace

from app.modules.fraud import estimator
from app.modules.fraud import service as fraud
from evals.paper.common import ci95, save

TRUE_PRICE = 20
DEAR_DAY_PRICE = 22
DEAR_DAY_PROB = 0.15
BAND = (Decimal("15.00"), Decimal("30.00"))
WEEKS = 16
WINDOW_DAYS = fraud.PATTERN_WINDOW_DAYS


class _NearLineSession:
    """Stands in for AsyncSession in fraud.evaluate_near_threshold."""

    def __init__(self, rows, already_open: bool):
        self._rows = rows
        self._open = already_open
        self.added = []

    async def execute(self, _stmt):
        return self._rows

    async def scalar(self, _stmt):
        return 1 if self._open else 0

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        return None


def reference_obj(price: Decimal) -> SimpleNamespace:
    # tolerance_pct / tolerance_abs at their schema defaults (0.400 / 20.00).
    return SimpleNamespace(reference_price=price, tolerance_pct=Decimal("0.400"),
                           tolerance_abs=Decimal("20.00"))


def honest_price(rng) -> int:
    return DEAR_DAY_PRICE if rng.random() < DEAR_DAY_PROB else TRUE_PRICE


async def run(estimator_name: str, attack_frac: float, strategy: str, seed: int,
        n_runners: int = 40, claims_per_week: float = 1.5) -> dict:
    rng = random.Random(seed * 1009 + int(attack_frac * 100))
    runners = [str(uuid.UUID(int=i + 1)) for i in range(n_runners)]
    n_att = round(attack_frac * n_runners)
    attackers = set(runners[:n_att])
    rate = {r: claims_per_week for r in runners}
    if strategy == "volume" and attackers:
        # One attacker files ten times as many claims as anyone else.
        rate[runners[0]] = claims_per_week * 10

    ref = Decimal("20.00")
    claims: list[dict] = []     # {runner, day, price, verdict, delta, threshold, eligible}
    by_runner_claims: dict[str, list[dict]] = {r: [] for r in runners}
    near_flagged: set[str] = set()
    trajectory = [float(ref)]
    proposals = 0
    excess_paid = 0.0
    excess_before_flag = 0.0
    honest_flagged = honest_total = 0
    # Per attacker: when the walking-the-line rule first fired, and what the
    # 30-day window looked like at that moment. This is what explains how a
    # 50 % inflator is caught by a 60 % rule.
    detection: dict[str, dict] = {}

    for week in range(WEEKS):
        for r in runners:
            k = _poisson(rng, rate[r])
            for _ in range(k):
                day = week * 7 + rng.uniform(0, 7)
                truth = honest_price(rng)
                tol = fraud.effective_tolerance(reference_obj(ref))
                line_price = (ref + tol * Decimal("0.95")).quantize(Decimal("1"),
                                                                    rounding="ROUND_FLOOR")
                if r in attackers and strategy == "overt":
                    price = Decimal(30)
                elif r in attackers and strategy == "evasive":
                    # Inflate only every other claim, so that the share of
                    # near-line claims stays under the 60 % the rule requires.
                    price = line_price if rng.random() < 0.5 else Decimal(truth)
                elif r in attackers:  # "line" and "volume"
                    price = line_price
                else:
                    price = Decimal(truth)
                j = fraud.judge(price, 1, reference_obj(ref))
                claim = {"runner": r, "day": day, "price": price, "verdict": j.verdict,
                         "delta": j.delta_abs, "threshold": j.threshold, "eligible": j.eligible}
                claims.append(claim)
                by_runner_claims[r].append(claim)
                if r in attackers:
                    excess_paid += float(j.eligible) - truth
                    if r not in near_flagged:
                        excess_before_flag += float(j.eligible) - truth
                else:
                    honest_total += 1
                    honest_flagged += j.verdict == "FLAGGED"
                # The walking-the-line rule runs on every submission, as in submit_claims.
                rows = [(c["delta"], c["threshold"]) for c in by_runner_claims[r]
                        if c["verdict"] != "FLAGGED"
                        and c["threshold"] is not None and day - c["day"] <= WINDOW_DAYS]
                sess = _NearLineSession(rows, already_open=r in near_flagged)
                flag = await _near(sess, r)
                if flag is not None:
                    if r not in near_flagged:
                        near = sum(1 for d, t in rows
                                   if d >= t * fraud.NEAR_THRESHOLD_SHARE)
                        detection[r] = {"day": round(day, 2), "window_claims": len(rows),
                                        "near_claims": near,
                                        "share": round(near / len(rows), 3)}
                    near_flagged.add(r)

        # Weekly refresh, from the last 30 days.
        now = (week + 1) * 7
        window = [c for c in claims if now - c["day"] <= WINDOW_DAYS]
        new_ref, proposal = estimate(estimator_name, window, near_flagged)
        proposals += proposal
        if new_ref is not None:
            ref = new_ref
        trajectory.append(float(ref))

    return {
        "estimator": estimator_name, "attack_frac": attack_frac, "strategy": strategy,
        "seed": seed, "final_reference": float(ref), "trajectory": trajectory,
        "excess_paid_to_attackers": round(excess_paid, 2),
        "excess_paid_before_flag": round(excess_before_flag, 2),
        "attacker_detection": [detection.get(a) for a in sorted(attackers)],
        "attacker_lifetime_share": [
            round(sum(1 for c in by_runner_claims[a] if c["threshold"] is not None
                      and c["delta"] >= c["threshold"] * fraud.NEAR_THRESHOLD_SHARE)
                  / max(1, len(by_runner_claims[a])), 3)
            for a in sorted(attackers)],
        "honest_false_flag_rate": honest_flagged / honest_total if honest_total else 0.0,
        "attackers": n_att,
        "attackers_flagged_near_line": len(near_flagged & attackers),
        "honest_flagged_near_line": len(near_flagged - attackers),
        "proposals": proposals,
    }


async def _near(sess, runner_id):
    runner = SimpleNamespace(id=uuid.UUID(runner_id))
    return await fraud.evaluate_near_threshold(sess, uuid.uuid4(), runner)


def estimate(name: str, window: list[dict], suspects: set[str]):
    if not window:
        return None, 0
    if name == "mean_all":
        return Decimal(str(round(mean(float(c["price"]) for c in window), 2))), 0
    unflagged = [c for c in window if c["verdict"] != "FLAGGED"]
    if not unflagged:
        return None, 0
    if name == "mean_unflagged":
        return Decimal(str(round(mean(float(c["price"]) for c in unflagged), 2))), 0
    if name == "median_pooled":
        return Decimal(str(median(float(c["price"]) for c in unflagged))).quantize(
            Decimal("0.01")), 0
    exclude_suspects = name in ("robust_excl", "production")
    use_band = name in ("robust_band", "production")
    by_runner: dict[str, list[Decimal]] = {}
    for c in unflagged:
        if exclude_suspects and c["runner"] in suspects:
            continue  # refresh_reference: suspects get no vote on the line
        by_runner.setdefault(c["runner"], []).append(c["price"])
    if use_band:
        est = estimator.estimate_reference(by_runner, BAND[0], BAND[1])
    else:
        est = estimator.estimate_reference(by_runner)
    return (est.value if est.usable else None), int(est.needs_proposal)


def _poisson(rng, lam):
    L, k, p = math.exp(-lam), 0, 1.0
    while True:
        p *= rng.random()
        if p <= L:
            return k
        k += 1


SEEDS = range(1, 31)


def _c(values):
    c = ci95([float(v) for v in values])
    return {k: (round(v, 4) if isinstance(v, float) else v) for k, v in c.items()}


async def main() -> dict:
    names = ["mean_all", "mean_unflagged", "median_pooled", "robust", "robust_excl",
             "robust_band", "production"]
    out = {"seeds": len(SEEDS), "sweep": [], "trajectories": [], "detection": []}
    for strategy in ("line", "evasive", "overt", "volume"):
        fracs = (0.025,) if strategy == "volume" else (0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6)
        for f in fracs:
            for name in names:
                runs = [await run(name, f, strategy, s) for s in SEEDS]
                det = [d for r in runs for d in r["attacker_detection"]]
                caught = [d for d in det if d is not None]
                row = {
                    "estimator": name, "strategy": strategy, "attack_frac": f,
                    "final_reference": _c(r["final_reference"] for r in runs),
                    "final_reference_max": max(r["final_reference"] for r in runs),
                    "excess_paid": _c(r["excess_paid_to_attackers"] for r in runs),
                    "excess_paid_before_flag": _c(r["excess_paid_before_flag"] for r in runs),
                    "honest_false_flag_rate": _c(r["honest_false_flag_rate"] for r in runs),
                    "attackers_flagged_near_line": _c(
                        r["attackers_flagged_near_line"] for r in runs),
                    "honest_flagged_near_line": _c(r["honest_flagged_near_line"] for r in runs),
                    "attackers": runs[0]["attackers"],
                    "attacker_detect_rate": (len(caught) / len(det)) if det else None,
                    "days_to_detection": _c(d["day"] for d in caught) if caught else None,
                    "proposals": _c(r["proposals"] for r in runs),
                }
                out["sweep"].append(row)
                print({k: (v["mean"] if isinstance(v, dict) else v) for k, v in row.items()},
                      flush=True)
                if name == "production" and strategy in ("line", "evasive") and det:
                    life = [x for r in runs for x in r["attacker_lifetime_share"]]
                    out["detection"].append({
                        "strategy": strategy, "attack_frac": f,
                        "detect_rate": len(caught) / len(det),
                        "share_at_flag": _c(d["share"] for d in caught) if caught else None,
                        "window_claims_at_flag": _c(d["window_claims"] for d in caught)
                        if caught else None,
                        "near_claims_at_flag": _c(d["near_claims"] for d in caught)
                        if caught else None,
                        "lifetime_share": _c(life),
                        "lifetime_share_at_or_above_rule": sum(
                            1 for x in life if x >= float(fraud.NEAR_THRESHOLD_MIN_RATIO))
                        / len(life),
                    })
                if f in (0.3, 0.6) and strategy in ("line", "evasive"):
                    out["trajectories"].append({"estimator": name, "strategy": strategy,
                                                "attack_frac": f,
                                                "trajectories": [r["trajectory"] for r in runs]})
    save("exp3_reference", out)
    return out


if __name__ == "__main__":
    asyncio.run(main())
