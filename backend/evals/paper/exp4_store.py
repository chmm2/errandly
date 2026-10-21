"""Experiment 4: one item, two shops, and the runners caught between them.

The campus reference for Chicken Puff is 20. One canteen sells it at 20, a
second at 30. An honest runner at the dearer counter claims 30, which is 10
over a reference whose allowance is 8: flagged, and the excess withheld, for
telling the truth.

fraud.service.store_adjusted_reference moves the reference toward what a shop
is observed to charge, weighted by how many DISTINCT runners have reported
from it. This measures (a) how many independent reports it takes before the
honest runner at the dear shop stops being flagged, and (b) how many
colluding runners it takes to move a cheap shop's reference upward.

Both use the production functions; only the claim query is replaced.

Run: python -m evals.paper.exp4_store
"""

from __future__ import annotations

import asyncio
import uuid
from decimal import Decimal
from types import SimpleNamespace

from app.modules.fraud import service as fraud
from evals.paper.common import save

REF = SimpleNamespace(reference_price=Decimal("20.00"), tolerance_pct=Decimal("0.400"),
                      tolerance_abs=Decimal("20.00"))


class _StoreClaims:
    """Stands in for AsyncSession in store_adjusted_reference: (runner_id, price) rows."""

    def __init__(self, rows):
        self._rows = rows

    async def execute(self, _stmt):
        return self._rows


def runner(i: int) -> uuid.UUID:
    return uuid.UUID(int=10_000 + i)


async def adjusted(rows) -> Decimal:
    return await fraud.store_adjusted_reference(
        _StoreClaims(rows), uuid.uuid4(), "chicken puff", "label:dear canteen", REF
    )


async def honest_dear_shop() -> list[dict]:
    """n distinct honest runners have each reported the shop's price at a dear
    shop (some more than once). Is the next honest claim at that price flagged?
    Shop prices of 25 (inside the allowance), 30, 40 and 60 (beyond the 2.5x
    drift cap) against a campus reference of 20."""
    out = []
    for shop_price in (25, 30, 40, 60):
        price = Decimal(f"{shop_price}.00")
        for n in (0, 1, 2, 3, 4, 6, 10, 20, 40):
            rows = []
            for i in range(n):
                rows += [(runner(i), price)] * (1 + i % 3)
            ref_store = await adjusted(rows) if n else fraud._money(REF.reference_price)
            pooled = fraud.judge(price, 1, REF)
            store = fraud.judge(price, 1, REF, ref_override=ref_store)
            out.append({
                "shop_price": shop_price,
                "distinct_reporters": n, "store_reference": float(ref_store),
                "pooled_verdict": pooled.verdict, "store_verdict": store.verdict,
                "withheld_pooled": float(price - pooled.eligible),
                "withheld_store": float(price - store.eligible),
            })
    return out


async def collusion_on_cheap_shop() -> list[dict]:
    """h honest runners report 20 at a cheap shop; k colluders report an
    inflated price there, each filing `volume` claims. Does the shop's
    reference move, does a colluder's claim pass, and how much over the true
    price is paid per claim once it does?"""
    out = []
    for inflated in (30, 40, 50):
        price = Decimal(f"{inflated}.00")
        for volume in (1, 10, 50):
            for h in (0, 1, 3, 5, 10, 20):
                for k in (1, 2, 3, 5, 8, 10, 11, 15, 20):
                    rows = [(runner(i), Decimal("20.00")) for i in range(h) for _ in range(2)]
                    rows += [(runner(100 + j), price) for j in range(k) for _ in range(volume)]
                    ref_store = await adjusted(rows)
                    j = fraud.judge(price, 1, REF, ref_override=ref_store)
                    out.append({"inflated_price": inflated, "claims_per_colluder": volume,
                                "honest_reporters": h, "colluders": k,
                                "store_reference": float(ref_store),
                                "colluder_verdict": j.verdict,
                                "overpaid_per_claim": float(j.eligible - Decimal("20.00")),
                                # Whether the claim still counts toward the
                                # walking-the-line rule, judged against the
                                # shop-adjusted reference it was held to.
                                "near_line": j.threshold is not None and j.delta_abs
                                >= j.threshold * fraud.NEAR_THRESHOLD_SHARE})
    return out


async def cold_start() -> list[dict]:
    """A shop nobody has reported from yet, then its first reporters. The
    store estimate needs STORE_MIN_RUNNERS distinct runners before it moves at
    all; until then every claim is judged against the campus reference."""
    out = []
    for n in range(0, 8):
        rows = [(runner(i), Decimal("30.00")) for i in range(n)]
        ref_store = await adjusted(rows) if n else fraud._money(REF.reference_price)
        out.append({"distinct_reporters": n, "store_reference": float(ref_store)})
    return out


async def main() -> dict:
    out = {
        "constants": {"STORE_PRIOR": str(fraud.STORE_PRIOR),
                      "STORE_MIN_RUNNERS": fraud.STORE_MIN_RUNNERS,
                      "STORE_MAX_DRIFT": str(fraud.STORE_MAX_DRIFT),
                      "tolerance": str(fraud.effective_tolerance(REF))},
        "honest_dear_shop": await honest_dear_shop(),
        "collusion_on_cheap_shop": await collusion_on_cheap_shop(),
        "cold_start": await cold_start(),
    }
    for r in out["honest_dear_shop"]:
        print(r)
    for r in out["collusion_on_cheap_shop"]:
        if r["claims_per_colluder"] == 10 and r["inflated_price"] == 30:
            print(r)
    for r in out["cold_start"]:
        print(r)
    save("exp4_store", out)
    return out


if __name__ == "__main__":
    asyncio.run(main())
