"""Robust reference-price estimation.

The naive version of "keep the price list up to date automatically" is to
average recent claims. That closes a loop: inflated claims raise the average,
the raised average makes the next inflated claim look normal, and the detector
teaches itself to accept the fraud it exists to catch.

Three defences, in order of how much they matter:

1. **One runner, one vote.** We take each runner's own median first, then the
   median across runners. A runner who claims 40 for a 20-rupee puff two
   hundred times contributes exactly one 40 to the outer median - volume buys
   no influence. This is the defence that does the real work.
2. **Outlier rejection before estimating.** MAD-based, so the estimate is
   computed from the honest cluster rather than being dragged toward it.
3. **The admin band is a hard stop.** An estimate outside the band never
   applies; it becomes a proposal for a human. Bounds cannot be moved by the
   data they bound.

Nothing here is learned. Robust statistics is the right tool for a scalar with
an adversary attached, and it has the property a learned model would not: you
can explain to a suspended student exactly why the number is what it is.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from statistics import median

# A reference cannot be estimated from thin air. Below these floors the item
# stays NO_REFERENCE and nobody gets flagged for it.
MIN_DISTINCT_RUNNERS = 3
MIN_SAMPLES = 5

# Scale factor making MAD comparable to a standard deviation for normal data.
MAD_SCALE = Decimal("1.4826")
# Points more than this many robust deviations out are dropped before estimating.
OUTLIER_SIGMA = Decimal("3")

# How close to a band edge the estimate must sit before we ask an admin whether
# the band itself has gone stale.
BAND_EDGE_MARGIN = Decimal("0.05")
# Width of the band a proposal suggests, either side of the observed median.
PROPOSED_BAND_SPREAD = Decimal("0.25")


@dataclass(frozen=True)
class Estimate:
    """Outcome of one estimation pass over an item's claims."""

    value: Decimal | None
    observed_median: Decimal | None
    sample_count: int
    distinct_runners: int
    outliers_dropped: int
    # Set when there is a defensible estimate but the band forbids applying it.
    needs_proposal: bool = False
    reason: str = ""

    @property
    def usable(self) -> bool:
        return self.value is not None


def _median(values: list[Decimal]) -> Decimal:
    return Decimal(str(median(values)))


def _reject_outliers(values: list[Decimal]) -> tuple[list[Decimal], int]:
    """Drop points far from the median, measured in median absolute deviations.

    MAD rather than standard deviation: an extreme claim inflates a standard
    deviation enough to smuggle itself back inside the cut, which is precisely
    the failure we cannot afford.
    """
    if len(values) < 3:
        return values, 0
    med = _median(values)
    deviations = [abs(v - med) for v in values]
    mad = _median(deviations)
    if mad == 0:
        # Every point identical bar a few - keep the exact matches only.
        kept = [v for v in values if v == med]
        return (kept, len(values) - len(kept)) if kept else (values, 0)
    limit = OUTLIER_SIGMA * MAD_SCALE * mad
    kept = [v for v in values if abs(v - med) <= limit]
    return (kept, len(values) - len(kept)) if kept else (values, 0)


def estimate_reference(
    claims_by_runner: dict[str, list[Decimal]],
    band_min: Decimal | None = None,
    band_max: Decimal | None = None,
) -> Estimate:
    """Estimate what an item actually costs, given claims grouped by runner.

    `claims_by_runner` must already exclude claims previously judged FLAGGED -
    a claim we called fraudulent must never come back as evidence of the going
    rate. The caller owns that filter because it owns the query.
    """
    total_samples = sum(len(v) for v in claims_by_runner.values())
    distinct = len(claims_by_runner)

    if distinct < MIN_DISTINCT_RUNNERS or total_samples < MIN_SAMPLES:
        return Estimate(
            value=None,
            observed_median=None,
            sample_count=total_samples,
            distinct_runners=distinct,
            outliers_dropped=0,
            reason=(
                f"insufficient evidence: {total_samples} claims from {distinct} runners "
                f"(need {MIN_SAMPLES} from {MIN_DISTINCT_RUNNERS})"
            ),
        )

    # One vote each: collapse every runner to their own median first.
    per_runner = [_median(v) for v in claims_by_runner.values() if v]
    kept, dropped = _reject_outliers(per_runner)
    observed = _median(kept).quantize(Decimal("0.01"))

    if band_min is None or band_max is None:
        return Estimate(
            value=observed,
            observed_median=observed,
            sample_count=total_samples,
            distinct_runners=distinct,
            outliers_dropped=dropped,
            reason="no band set; estimate stands on its own",
        )

    if observed < band_min or observed > band_max:
        # Outside the band the estimate is a question for a human, not an update.
        return Estimate(
            value=None,
            observed_median=observed,
            sample_count=total_samples,
            distinct_runners=distinct,
            outliers_dropped=dropped,
            needs_proposal=True,
            reason=(
                f"observed median {observed} sits outside the approved band "
                f"[{band_min}, {band_max}] - the band may be stale"
            ),
        )

    # Inside the band, but pressed against an edge: apply it AND ask.
    span = band_max - band_min
    margin = span * BAND_EDGE_MARGIN
    at_edge = span > 0 and (observed <= band_min + margin or observed >= band_max - margin)

    return Estimate(
        value=observed,
        observed_median=observed,
        sample_count=total_samples,
        distinct_runners=distinct,
        outliers_dropped=dropped,
        needs_proposal=at_edge,
        reason=(
            f"observed median {observed} is near a band edge [{band_min}, {band_max}]"
            if at_edge
            else f"observed median {observed} sits comfortably inside the band"
        ),
    )


def propose_band(observed: Decimal) -> tuple[Decimal, Decimal]:
    """Suggest a band around an observed median, for an admin to approve."""
    lo = (observed * (1 - PROPOSED_BAND_SPREAD)).quantize(Decimal("0.01"))
    hi = (observed * (1 + PROPOSED_BAND_SPREAD)).quantize(Decimal("0.01"))
    return (max(lo, Decimal("0.01")), hi)
