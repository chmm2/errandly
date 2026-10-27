"""Export the simulated datasets behind the paper as plain CSV files.

The experiments generate their data from seeds rather than reading a fixed
dataset, so "the dataset" is whatever a given seed produces. This script writes
that data out for the representative seeds, using the same code and seeds as the
reported runs, so a reader can inspect it without running a simulation:

  campus_seed1/       the simulated campus and one semester of errands, routine
                      and coordinated regimes (exp2, exp6)
  price_claims/       every claim of one 16-week run per attack (exp3)
  escrow_orders/      the 3,000 orders of escrow seed 1 (exp7)
  item_names/         every hand-written item-name variant and adversarial name,
                      with how the old and the deployed rule treated it (exp9)
  shop_pooling/       the shop-pooling grid (exp4)

Run (from the repository root):
  docker compose run --rm --no-deps -T -v "$(pwd)/paper-artifacts:/paper-artifacts" \
    -e LLM_PROVIDER= backend python -m evals.paper.export_datasets
"""

from __future__ import annotations

import asyncio
import csv
import json
from pathlib import Path

from evals.paper import exp3_reference, exp7_escrow, exp9_normalize
from evals.paper.campus import Campus, Config, Semester
from evals.paper.common import RESULTS_DIR, uid
from evals.paper.exp2_collusion import REGIMES

OUT = RESULTS_DIR.parent / "datasets"


def write(path: Path, header: list[str], rows) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        for row in rows:
            w.writerow(row)
            n += 1
    print(f"{path.relative_to(OUT)}: {n} rows")
    return n


def campus(seed: int = 1) -> None:
    base = OUT / f"campus_seed{seed}"
    c = Campus(Config(seed=seed))
    write(base / "students.csv",
          ["student_id", "hostel_block", "home_x_m", "home_y_m", "planted_group_id",
           "planted_group_kind", "friends", "closure"],
          ([uid(i), c.block[i], round(c.home[i][0], 1), round(c.home[i][1], 1),
            c.group_of[i] if c.group_of[i] >= 0 else "", c.kind[i] or "",
            c.degree[i], round(c.closure[i], 4)] for i in range(c.n)))
    write(base / "friendships.csv", ["student_a", "student_b"],
          ([uid(a), uid(b)] for a, b in c.edges))
    for regime in ("routine", "coordinated"):
        cfg = Config(seed=seed, **REGIMES[regime])
        sem = Semester(c, cfg)
        sem.run()
        write(base / f"errands_{regime}.csv",
              ["errand_id", "posted_s", "requester", "kind", "reward_rs", "collect_rs",
               "first_tier", "exploring", "winner", "wait_s", "winner_hops"],
              ([f"e{e['eid']}", round(e["t"], 1), uid(e["req"]), e["kind"], e["reward"],
                e["collect"], "" if e["first_tier"] is None else e["first_tier"],
                int(e["exploring"]), "" if e["winner"] is None else uid(e["winner"]),
                "" if e["wait_s"] is None else round(e["wait_s"], 1),
                "" if e["winner_hops"] is None else e["winner_hops"]]
               for e in sem.errands))
        write(base / f"payments_{regime}.csv",
              ["errand_id", "payer", "payee", "amount_rs", "at"],
              ([p["eid"], p["src"], p["dst"], p["amount"], p["at"]] for p in sem.payments))

        def rounds(sem=sem):
            for j, row in enumerate(sem.offer_logs):
                for cand in row.candidates:
                    yield [f"r{j}", str(row.requester_id), int(row.exploring),
                           "" if row.accepted_runner_id is None else str(row.accepted_runner_id),
                           cand["runner_id"], cand["rank"], cand["distance_m"],
                           "" if cand.get("hops") is None else cand["hops"],
                           cand["trust"], cand["effective"]]
        write(base / f"offer_rounds_{regime}.csv",
              ["round_id", "requester", "exploring", "accepted_by", "candidate", "rank",
               "distance_m", "hops", "trust", "effective_score_m"], rounds())


async def price_claims(seed: int = 1) -> None:
    for strategy, frac in (("line", 0.3), ("evasive", 0.3), ("overt", 0.3), ("volume", 0.025)):
        r = await exp3_reference.run("production", frac, strategy, seed, keep_claims=True)
        write(OUT / "price_claims" / f"{strategy}_{int(frac * 1000):03d}_seed{seed}.csv",
              ["runner", "attacker", "day", "true_price_rs", "claimed_rs",
               "reference_in_force_rs", "verdict", "rs_over_reference", "allowance_rs",
               "reimbursed_rs", "runner_already_flagged"],
              ([c["runner"], int(c["attacker"]), round(c["day"], 2), c["true_price"],
                float(c["price"]), c["reference"], c["verdict"],
                "" if c["delta"] is None else float(c["delta"]),
                "" if c["threshold"] is None else float(c["threshold"]),
                float(c["eligible"]), int(c["runner_flagged"])]
               for c in sorted(r["claims"], key=lambda c: c["day"])))
        write(OUT / "price_claims" / f"{strategy}_{int(frac * 1000):03d}_seed{seed}_reference.csv",
              ["week", "reference_rs"], enumerate(r["trajectory"]))


def escrow(seed: int = 1) -> None:
    orders = exp7_escrow.make_orders(seed, 3000, exp7_escrow.PRICE_DRIFT)

    def rows():
        for k, (mrp, loose, reward, eligible) in enumerate(orders):
            yield [f"o{k}", reward, sum(mrp), len(mrp),
                   sum(price * q for (_, price), q in loose),
                   "; ".join(f"{q} x {name} @ {price}" for (name, price), q in loose),
                   float(eligible)]
    write(OUT / "escrow_orders" / f"orders_seed{seed}.csv",
          ["order_id", "reward_rs", "mrp_total_rs", "mrp_items", "loose_total_at_reference_rs",
           "loose_lines", "eligible_reimbursement_rs"], rows())


def item_names() -> None:
    from app.modules.fraud.normalize import normalize, resolve_key
    keys = [normalize(i) for i in exp9_normalize.ITEMS]

    def variants():
        for item, names in exp9_normalize.VARIANTS.items():
            for name in names:
                key, matched = resolve_key(name, keys)
                yield [item, name, key, int(matched), int(matched and key == normalize(item))]
    write(OUT / "item_names" / "variants.csv",
          ["intended_item", "typed_name", "resolved_key", "matched_a_priced_key", "correct"],
          variants())
    write(OUT / "item_names" / "must_not_merge.csv", ["typed_name", "resolved_key", "merged"],
          ([n, *(lambda k: [k[0], int(k[1])])(resolve_key(n, keys))]
           for n in exp9_normalize.MUST_NOT_MERGE))
    adv = exp9_normalize.adversarial()
    write(OUT / "item_names" / "adversarial.csv",
          ["intended_item", "attack_kind", "typed_name", "old_rule", "deployed_rule"],
          ([a["item"], a["kind"], a["name"], a["old"], a["new"]] for a in adv["attempts"]))


def shop_pooling() -> None:
    d = json.loads((RESULTS_DIR / "exp4_store.json").read_text())["results"]
    write(OUT / "shop_pooling" / "honest_dear_shop.csv",
          list(d["honest_dear_shop"][0]), (list(r.values()) for r in d["honest_dear_shop"]))
    write(OUT / "shop_pooling" / "colluders_cheap_shop.csv",
          list(d["collusion_on_cheap_shop"][0]),
          (list(r.values()) for r in d["collusion_on_cheap_shop"]))


async def main() -> None:
    campus()
    await price_claims()
    escrow()
    item_names()
    shop_pooling()


if __name__ == "__main__":
    asyncio.run(main())
