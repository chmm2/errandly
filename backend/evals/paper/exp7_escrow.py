"""Experiment 7: how much headroom an escrow hold needs, and on what.

The requester's money is held when the order is placed. A runner who finds a
loose-priced item dearer at the counter is owed more than the estimate, and if
that exceeds the hold the settlement consumer freezes the payout for review
(workers/consumers.py: payable > remaining hold). Headroom avoids that, at the
cost of locking money the order may not need.

Policies compared, all through the production ledger.place_hold arithmetic:
  none          no headroom
  non_mrp_16    16 % on the non-MRP subtotal only (production: escrow_buffer_pct,
                buffer_base = non-MRP total)
  whole_16      16 % on the whole spend estimate
  non_mrp_30    30 % on the non-MRP subtotal

Counter prices for non-MRP items are drawn from an assumed distribution (most
days the listed price, some days dearer). MRP items cost exactly their printed
price. Each non-MRP line is judged by the production fraud.judge, so an honest
overspend beyond the allowance is withheld at the reference, as in deployment.

Run: python -m evals.paper.exp7_escrow
"""

from __future__ import annotations

import asyncio
import random
import uuid
from contextlib import asynccontextmanager
from decimal import Decimal
from statistics import mean
from types import SimpleNamespace

from app.core.config import settings
from app.modules.fraud import service as fraud
from app.modules.ledger import service as ledger
from evals.paper.common import ci95, save

NON_MRP = [("chicken puff", 20), ("veg puff", 15), ("masala tea", 10), ("samosa", 15),
           ("veg sandwich", 35), ("cold coffee", 40)]
# Counter price as a multiple of the listed reference, and how often.
PRICE_DRIFT = [(1.00, 0.70), (1.10, 0.15), (1.20, 0.10), (1.35, 0.05)]
# A dearer world, for sensitivity: counters that drift more often and further.
PRICE_DRIFT_HEAVY = [(1.00, 0.50), (1.10, 0.20), (1.20, 0.15), (1.35, 0.10), (1.60, 0.05)]
DRIFTS = {"assumed": PRICE_DRIFT, "heavy": PRICE_DRIFT_HEAVY}


class _LedgerSession:
    """Just enough AsyncSession for place_hold: a funded wallet, no conflicts."""

    async def execute(self, _stmt):
        return None

    async def scalar(self, _stmt):
        return Decimal("1000000")

    @asynccontextmanager
    async def _nested(self):
        yield

    def begin_nested(self):
        return self._nested()

    def add(self, _obj):
        return None

    async def flush(self):
        return None

    async def get(self, *_a):
        return None


def drift(rng, table=PRICE_DRIFT) -> float:
    x, acc = rng.random(), 0.0
    for mult, p in table:
        acc += p
        if x <= acc:
            return mult
    return table[-1][0]


def basket(rng):
    mrp = [rng.choice((10, 20, 30, 45, 60, 99, 150)) for _ in range(rng.randint(0, 4))]
    loose = [(rng.choice(NON_MRP), rng.randint(1, 3)) for _ in range(rng.randint(1, 4))]
    reward = rng.choice((20, 25, 30, 40, 50))
    return mrp, loose, reward


async def hold_for(mrp, loose, reward, policy: str, pct_override: float | None = None):
    mrp_total = Decimal(sum(mrp))
    non_mrp_total = Decimal(sum(price * q for (_, price), q in loose))
    items_total = mrp_total + non_mrp_total
    if policy == "none":
        pct, base = 0.0, Decimal(0)
    elif policy == "non_mrp_16":
        pct, base = settings.escrow_buffer_pct, non_mrp_total
    elif policy == "whole_16":
        pct, base = settings.escrow_buffer_pct, items_total
    elif policy == "non_mrp_30":
        pct, base = 0.30, non_mrp_total
    elif policy == "non_mrp":
        pct, base = pct_override, non_mrp_total
    elif policy == "whole":
        pct, base = pct_override, items_total
    else:
        raise ValueError(policy)
    hold = await ledger.place_hold(
        _LedgerSession(), errand_id=uuid.uuid4(), requester_id=uuid.uuid4(),
        items_total=items_total, reward=Decimal(reward), collect_amount=Decimal(0),
        buffer_pct=pct, buffer_base=base,
    )
    return Decimal(str(hold.amount))


def make_orders(seed: int, n_orders: int, table) -> list:
    rng = random.Random(23 + 1000 * seed)
    orders = []
    for _ in range(n_orders):
        mrp, loose, reward = basket(rng)
        # What the runner actually paid, and what the judge will reimburse.
        eligible = Decimal(sum(mrp))
        for (_name, price), q in loose:
            paid = Decimal(str(round(price * drift(rng, table))))
            ref = SimpleNamespace(reference_price=Decimal(price),
                                  tolerance_pct=Decimal("0.400"), tolerance_abs=Decimal("20.00"))
            eligible += fraud.judge(paid, q, ref).eligible
        orders.append((mrp, loose, reward, eligible))
    return orders


async def score(orders, policy, pct=None) -> dict:
    frozen, locked, slack = 0, [], []
    for mrp, loose, reward, eligible in orders:
        hold = await hold_for(mrp, loose, reward, policy, pct_override=pct)
        payable = eligible + Decimal(reward)
        frozen += payable > hold
        locked.append(float(hold))
        slack.append(float(max(Decimal(0), hold - payable)))
    n = len(orders)
    return {"freeze_rate": frozen / n, "mean_hold": mean(locked),
            "mean_unneeded_lock": mean(slack),
            "p95_unneeded_lock": sorted(slack)[int(0.95 * n)]}


def _c(values):
    c = ci95(list(values))
    return {k: (round(v, 4) if isinstance(v, float) else v) for k, v in c.items()}


async def main(n_orders: int = 3000, seeds=tuple(range(1, 31))) -> dict:
    out = {"orders_per_seed": n_orders, "seeds": len(seeds),
           "escrow_buffer_pct": settings.escrow_buffer_pct, "policies": [], "frontier": []}
    for drift_name, table in DRIFTS.items():
        books = [make_orders(sd, n_orders, table) for sd in seeds]
        for policy in ("none", "non_mrp_16", "whole_16", "non_mrp_30"):
            runs = [await score(o, policy) for o in books]
            row = {"drift": drift_name, "policy": policy,
                   **{k: _c(r[k] for r in runs) for k in runs[0]}}
            out["policies"].append(row)
            print(drift_name, policy, {k: v["mean"] for k, v in row.items()
                                       if isinstance(v, dict)}, flush=True)
        # The trade-off curve: freeze rate against money locked for nothing, as
        # the headroom percentage moves, for each choice of what it covers.
        for base in ("non_mrp", "whole"):
            for pct in (0.0, 0.05, 0.10, 0.16, 0.20, 0.25, 0.30, 0.40, 0.50):
                runs = [await score(o, base, pct) for o in books[:10]]
                out["frontier"].append({
                    "drift": drift_name, "base": base, "pct": pct,
                    "freeze_rate": _c(r["freeze_rate"] for r in runs),
                    "mean_unneeded_lock": _c(r["mean_unneeded_lock"] for r in runs)})
        save("exp7_escrow", out)
    return out


if __name__ == "__main__":
    asyncio.run(main())
