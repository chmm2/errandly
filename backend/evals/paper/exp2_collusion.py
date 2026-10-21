"""Experiment 2: separating collusion rings from honest close-knit groups.

Each trial simulates one semester on a 1,200-student campus (see campus.py)
with collusion rings and honest groups planted as identical cliques, loads the
resulting FRIEND and PAID edges into the throwaway Neo4j, and runs:

  * the production graph metrics      social.projection.refresh_graph_metrics
  * the production circulation job    fraud.collusion.refresh_circulation
  * the production ring search        fraud.collusion.find_rings
  * the production policy test        fraud.policy.excess_for_group

against baselines that each use one kind of evidence, plus two standard
graph-mining baselines (a FRAUDAR-style densest-block search on the payment
graph, and label-propagation communities filtered by internal money). The
policy test is run twice: with the router's own logged scores (the original
rule) and with the acceptance model fitted to logged acceptances by people
outside every candidate ring (the deployed rule). Ground truth is the set of
planted ring members.

Run:
  python -m evals.paper.exp2_collusion main
  python -m evals.paper.exp2_collusion sweeps
"""

from __future__ import annotations

import asyncio
import heapq
import math
import random
import sys
import time
import uuid as _uuid
from dataclasses import asdict, replace

from app.modules.fraud import collusion, policy
from app.modules.social.projection import refresh_graph_metrics
from app.modules.social.service import CLOSURE_KNEE
from evals.paper import neo
from evals.paper.campus import Campus, Config, Semester
from evals.paper.common import attach_graph_warning_counter, ci95, save, uid

_CAMPUS_CACHE: dict[int, Campus] = {}


def campus_for(cfg: Config) -> Campus:
    if cfg.seed not in _CAMPUS_CACHE:
        _CAMPUS_CACHE[cfg.seed] = Campus(cfg)
    return _CAMPUS_CACHE[cfg.seed]


class _OfferLogSession:
    """Stands in for AsyncSession in policy.excess_for_group.

    The production query selects OfferLog rows whose requester is a member of
    the group, inside the money window. The rows handed back here are exactly
    those, already filtered the same way.
    """

    def __init__(self, rows):
        self._rows = rows

    async def scalars(self, _stmt):
        return iter(self._rows)


def lcc(adj, u) -> float:
    ns = list(adj[u])
    d = len(ns)
    if d < 2:
        return 0.0
    links = 0
    for i in range(d):
        ai = adj[ns[i]]
        for j in range(i + 1, d):
            if ns[j] in ai:
                links += 1
    return 2.0 * links / (d * (d - 1))


def any_payment_cycles(payments) -> set[str]:
    """Baseline: find_rings' leg rule and SCC search, without the friendship test."""
    value: dict[tuple[str, str], float] = {}
    errands: dict[tuple[str, str], set[str]] = {}
    for p in payments:
        k = (p["src"], p["dst"])
        value[k] = value.get(k, 0.0) + p["amount"]
        errands.setdefault(k, set()).add(p["eid"])
    nodes: set[str] = set()
    adj: dict[str, set[str]] = {}
    for (a, b), v in value.items():
        txns = len(errands[(a, b)])
        substantial = v >= collusion.MIN_RING_LEG_VALUE or txns >= collusion.MIN_RING_LEG_TXNS
        if txns < collusion.MIN_RING_LAPS or not substantial:
            continue
        nodes.update((a, b))
        adj.setdefault(a, set()).add(b)
    flagged: set[str] = set()
    for comp in collusion.strongly_connected_components(nodes, adj):
        if len(comp) >= collusion.MIN_RING_SIZE:
            flagged |= comp
    return flagged


def fraudar_rank(payments, budget: int) -> tuple[set[str], int]:
    """FRAUDAR-style greedy peeling [Hooi et al., KDD 2016] on the payment graph.

    Payers and payees are the two sides of a bipartite graph; an edge carries
    the number of distinct errands on that pair, scaled by 1/log(payee degree
    + 5), the column weighting FRAUDAR uses against camouflage. Nodes are
    peeled greedily by lowest remaining incident weight.

    Returns two things. First, the accounts in the last `budget` positions of
    the peeling order: the densest core, cut at the true number of ring
    members. That budget is more than any deployment would know, so the
    baseline is given an advantage. Second, the size of the block FRAUDAR
    itself would report (the densest prefix), which on these graphs is the
    whole marketplace.
    """
    errands: dict[tuple[str, str], set[str]] = {}
    for p in payments:
        errands.setdefault((p["src"], p["dst"]), set()).add(p["eid"])
    indeg: dict[str, int] = {}
    for (_a, b) in errands:
        indeg[b] = indeg.get(b, 0) + 1
    w = {(a, b): len(v) / math.log(indeg[b] + 5) for (a, b), v in errands.items()}
    inc: dict[tuple[str, str], list] = {}
    prio: dict[tuple[str, str], float] = {}
    for (a, b), x in w.items():
        for node in (("s", a), ("d", b)):
            prio[node] = prio.get(node, 0.0) + x
            inc.setdefault(node, []).append((a, b))
    total = sum(w.values())
    alive = set(prio)
    heap = [(v, node) for node, v in prio.items()]
    heapq.heapify(heap)
    gone: set[tuple[str, str]] = set()
    order: list = []
    best, best_k = total / len(alive), 0
    while heap:
        v, node = heapq.heappop(heap)
        if node not in alive or abs(v - prio[node]) > 1e-12:
            continue
        alive.remove(node)
        order.append(node)
        for e in inc[node]:
            if e in gone:
                continue
            gone.add(e)
            total -= w[e]
            other = ("d", e[1]) if node[0] == "s" else ("s", e[0])
            if other in alive:
                prio[other] -= w[e]
                heapq.heappush(heap, (prio[other], other))
        if alive:
            g = total / len(alive)
            if g > best:
                best, best_k = g, len(order)
    block_size = len({node[1] for node in order[best_k:]})
    flagged: set[str] = set()
    for node in reversed(order):
        if len(flagged) >= budget:
            break
        flagged.add(node[1])
    return flagged, block_size


def label_propagation_money(adj, n, payments, seed: int, budget: int) -> tuple[set[str], int]:
    """Communities by asynchronous label propagation on the friend graph
    [Raghavan et al., Phys. Rev. E 2007], ranked by the share of their members'
    settled value that stays inside the community.

    Communities above the production circulation knee (0.6, with the same
    value and count floors) are what a deployment would flag; the second
    return value counts those accounts. The first is the top of the ranking
    cut at the true number of ring members, again an advantage no deployment
    has.
    """
    rng = random.Random(seed * 613 + 7)
    label = list(range(n))
    nodes = list(range(n))
    for _ in range(30):
        rng.shuffle(nodes)
        changed = False
        for u in nodes:
            if not adj[u]:
                continue
            counts: dict[int, int] = {}
            for v in adj[u]:
                counts[label[v]] = counts.get(label[v], 0) + 1
            top = max(counts.values())
            choice = rng.choice(sorted(k for k, c in counts.items() if c == top))
            if choice != label[u]:
                label[u] = choice
                changed = True
        if not changed:
            break
    comm_of = {uid(i): label[i] for i in range(n)}
    inside: dict[int, float] = {}
    touched: dict[int, float] = {}
    count: dict[int, int] = {}
    for p in payments:
        a, b = comm_of[p["src"]], comm_of[p["dst"]]
        for c in {a, b}:
            touched[c] = touched.get(c, 0.0) + p["amount"]
            count[c] = count.get(c, 0) + 1
        if a == b:
            inside[a] = inside.get(a, 0.0) + p["amount"]
    members: dict[int, list[int]] = {}
    for i in range(n):
        members.setdefault(label[i], []).append(i)
    ranked = []
    for c, ms in members.items():
        val = touched.get(c, 0.0)
        if len(ms) < collusion.MIN_RING_SIZE or val <= 0:
            continue
        share = inside.get(c, 0.0) / val
        eligible = (val >= collusion.MIN_CIRCULATION_VALUE
                    and count.get(c, 0) >= collusion.MIN_CIRCULATION_TXNS)
        ranked.append((share, eligible, ms))
    ranked.sort(key=lambda x: -x[0])
    above_knee = sum(len(ms) for share, ok, ms in ranked
                     if ok and share > collusion.CIRCULATION_KNEE)
    flagged: set[str] = set()
    for _share, _ok, ms in ranked:
        if len(flagged) >= budget:
            break
        flagged |= {uid(i) for i in ms}
    return flagged, above_knee


def confusion(flagged: set[str], truth: set[str], benign: set[str], n: int) -> dict:
    tp = len(flagged & truth)
    fp = len(flagged - truth)
    fn = len(truth - flagged)
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * p * r / (p + r) if p + r else 0.0
    return {
        "flagged": len(flagged), "tp": tp, "fp": fp, "fn": fn,
        "fp_benign_group": len(flagged & benign),
        "fp_other": fp - len(flagged & benign),
        "precision": p, "recall": r, "f1": f1,
        "fpr": fp / (n - len(truth)) if n > len(truth) else 0.0,
    }


async def run_trial(cfg: Config) -> dict:
    neo.assert_throwaway()
    warnings = attach_graph_warning_counter()
    t0 = time.perf_counter()
    campus = campus_for(cfg)
    sem = Semester(campus, cfg)
    sem.run()
    sem._refresh_circulation()
    t_sim = time.perf_counter() - t0

    n = campus.n
    truth = {uid(i) for i in range(n) if campus.kind[i] == "ring"}
    benign = {uid(i) for i in range(n) if campus.kind[i] == "benign"}

    t1 = time.perf_counter()
    await neo.wipe()
    await neo.load(
        [{"id": uid(i), "name": f"s{i}"} for i in range(n)],
        [{"a": uid(a), "b": uid(b), "since": None} for a, b in campus.edges],
        sem.payments,
    )
    t_load = time.perf_counter() - t1

    t2 = time.perf_counter()
    await refresh_graph_metrics()
    await collusion.refresh_circulation()
    rings = await collusion.find_rings()
    t_detect = time.perf_counter() - t2
    metrics = await neo.node_metrics()
    if warnings.count:
        raise RuntimeError(f"graph warnings during trial: {warnings.messages[:3]}")

    # The simulator's own transcriptions must agree with the production Cypher,
    # or the dispatch it simulated was not the dispatch production would do.
    diff_closure = max(abs(metrics[uid(i)]["closure"] - campus.closure[i]) for i in range(n))
    diff_circ = max(abs(metrics[uid(i)]["circulation"] - sem.circulation[i]) for i in range(n))

    by_req: dict[str, list] = {}
    for row in sem.offer_logs:
        by_req.setdefault(str(row.requester_id), []).append(row)

    # The deployed sweep fits the acceptance model on every round NOT posted
    # by a member of any candidate ring (sweep_collusion_rings ->
    # policy.fit_from_log(exclude=suspects)); the same filter is applied here.
    suspects = {str(m) for ring in rings for m in ring.members}
    t3 = time.perf_counter()
    model = policy.fit_acceptance_model(
        [r for r in sem.offer_logs if str(r.requester_id) not in suspects]
    )
    t_fit = time.perf_counter() - t3

    async def excess(members, fitted=False) -> policy.PolicyExcess | None:
        rows = [r for m in members for r in by_req.get(str(m), [])]
        return await policy.excess_for_group(
            _OfferLogSession(rows), list(members), model=model if fitted else None
        )

    ring_members: set[str] = set()
    kept_members: set[str] = set()
    kept_fitted: set[str] = set()
    found = []
    for ring in rings:
        ids = {str(m) for m in ring.members}
        ring_members |= ids
        ex = await excess(ring.members)
        exf = await excess(ring.members, fitted=True)
        suppressed = ex is not None and ex.explained
        suppressed_fitted = exf is not None and exf.explained
        if not suppressed:
            kept_members |= ids
        if not suppressed_fitted:
            kept_fitted |= ids
        found.append({
            "size": ring.size,
            "ring_members": len(ids & truth),
            "benign_members": len(ids & benign),
            "laps": ring.laps,
            "total_value": round(ring.total_value, 1),
            "z": None if ex is None else round(ex.z, 2),
            "rounds": None if ex is None else ex.rounds,
            "suppressed": suppressed,
            "z_fitted": None if exf is None else round(exf.z, 2),
            "suppressed_fitted": suppressed_fitted,
        })

    # The policy statistic for every planted group, flagged or not: the
    # distribution the threshold has to separate.
    group_z = []
    for g in campus.groups:
        members = [_uuid.UUID(uid(i)) for i in g["members"]]
        ex = await excess(members)
        exf = await excess(members, fitted=True)
        group_z.append({
            "z_fitted": None if exf is None else round(exf.z, 3),
            "expected_share_fitted": None if exf is None else round(exf.expected_share, 3),
            "kind": g["kind"], "size": len(members),
            "z": None if ex is None else round(ex.z, 3),
            "rounds": None if ex is None else ex.rounds,
            "observed_share": None if ex is None else round(ex.observed_share, 3),
            "expected_share": None if ex is None else round(ex.expected_share, 3),
        })

    adj = campus.adj
    fraud_flags, fraudar_block = fraudar_rank(sem.payments, budget=len(truth))
    lpa_flags, lpa_above_knee = label_propagation_money(
        adj, n, sem.payments, cfg.seed, budget=len(truth))
    detectors = {
        "structure_closure": {uid(i) for i in range(n)
                              if campus.degree[i] >= 2 and metrics[uid(i)]["closure"] > CLOSURE_KNEE},
        "structure_clustering": {uid(i) for i in range(n) if lcc(adj, i) > CLOSURE_KNEE},
        "money_circulation": {uid(i) for i in range(n)
                              if metrics[uid(i)]["circulation"] > collusion.CIRCULATION_KNEE},
        "structure_and_money": {uid(i) for i in range(n)
                                if campus.degree[i] >= 2
                                and metrics[uid(i)]["closure"] > CLOSURE_KNEE
                                and metrics[uid(i)]["circulation"] > collusion.CIRCULATION_KNEE},
        "payment_cycles_any": any_payment_cycles(sem.payments),
        "fraudar_payments": fraud_flags,
        "lpa_money": lpa_flags,
        "find_rings": ring_members,
        "find_rings_policy": kept_members,
        "find_rings_policy_fitted": kept_fitted,
    }
    scores = {name: confusion(flags, truth, benign, n) for name, flags in detectors.items()}

    def group_hit(flags, kind):
        gs = [g for g in campus.groups if g["kind"] == kind]
        return sum(1 for g in gs if any(uid(i) in flags for i in g["members"])) / len(gs)

    for name, flags in detectors.items():
        scores[name]["rings_touched"] = group_hit(flags, "ring")
        scores[name]["benign_groups_touched"] = group_hit(flags, "benign")

    done = [e for e in sem.errands if e["winner"] is not None]
    in_group = [e for e in done if campus.group_of[e["req"]] >= 0
                and campus.group_of[e["winner"]] == campus.group_of[e["req"]]
                and e["kind"] == "normal"]
    benign_normal = [e for e in done if campus.kind[e["req"]] == "benign" and e["kind"] == "normal"]
    return {
        "config": {k: v for k, v in asdict(cfg).items() if not isinstance(v, tuple)},
        "errands": len(sem.errands),
        "completed": len(done),
        "payments": len(sem.payments),
        "friend_edges": len(campus.edges),
        "mean_degree": round(2 * len(campus.edges) / n, 2),
        "benign_in_group_share": round(
            sum(1 for e in in_group if campus.kind[e["req"]] == "benign") / max(1, len(benign_normal)), 4
        ),
        "rings_found": len(rings),
        "fraudar_block_size": fraudar_block,
        "lpa_flagged_above_knee": lpa_above_knee,
        "fitted_model": None if model is None else {
            "coef": [round(c, 4) for c in model.coef], "rounds": model.rounds},
        "farm_value": round(sum(float(e["reward"]) for e in done if e["kind"] == "farm"), 1),
        "found": found,
        "group_z": group_z,
        "scores": scores,
        "check_max_diff_closure": diff_closure,
        "check_max_diff_circulation": diff_circ,
        "seconds": {"simulate": round(t_sim, 1), "load": round(t_load, 1),
                    "detect": round(t_detect, 2), "fit": round(t_fit, 2)},
    }


METRICS = ("precision", "recall", "f1", "fpr", "tp", "fp", "fn", "flagged",
           "fp_benign_group", "fp_other", "rings_touched", "benign_groups_touched")


def summarise(trials: list[dict]) -> dict:
    names = trials[0]["scores"].keys()
    out = {}
    for name in names:
        row = {}
        for metric in METRICS:
            c = ci95([t["scores"][name][metric] for t in trials])
            row[metric] = {k: (round(v, 4) if isinstance(v, float) else v) for k, v in c.items()}
        out[name] = row
    return out


# Behavioural regimes for the main table. None is claimed to be what a real
# campus does; between them they cover the cases each mechanism was built for
# and the cases that defeat it.
ROUTINE = {"favours_per_member": 0, "ring_mode": "naive"}
# More runners online and friends far likelier to accept each other's offers:
# the router, not anyone's intent, puts honest friends together.
BUSY = {"favours_per_member": 0, "ring_mode": "naive", "online_frac": 0.25,
        "friend_affinity": 4.0}
# Honest friends who deliberately route favours to each other.
FAVOURS = {"favours_per_member": 6, "ring_mode": "naive"}
# Rings that make the router offer each farmed errand to the partner first.
COORDINATED = {"favours_per_member": 0, "ring_mode": "stealth"}
# Both at once: honest favours and coordinated rings.
HARD = {"favours_per_member": 6, "ring_mode": "stealth"}
REGIMES = {"routine": ROUTINE, "busy": BUSY, "favours": FAVOURS,
           "coordinated": COORDINATED, "hard": HARD}


def _line(tag, r):
    s = r["scores"]
    return (f"{tag}: rings_found={r['rings_found']} "
            f"find_rings P/R={s['find_rings']['precision']:.2f}/{s['find_rings']['recall']:.2f} "
            f"+policy P/R={s['find_rings_policy']['precision']:.2f}/"
            f"{s['find_rings_policy']['recall']:.2f} "
            f"+fitted P/R={s['find_rings_policy_fitted']['precision']:.2f}/"
            f"{s['find_rings_policy_fitted']['recall']:.2f} "
            f"fraudar F1={s['fraudar_payments']['f1']:.2f} lpa F1={s['lpa_money']['f1']:.2f} "
            f"benign_in_group={r['benign_in_group_share']} "
            f"diff={r['check_max_diff_closure']:.1e}/{r['check_max_diff_circulation']:.1e} "
            f"t={r['seconds']}")


async def main_ablation(seeds=tuple(range(1, 31)), regimes=tuple(REGIMES),
                        tag: str = "") -> dict:
    """The main table. `regimes` and `tag` let it be split across processes,
    each saving exp2_main_<tag>.json; the figure script merges the parts."""
    out = {}
    for name in regimes:
        regime = REGIMES[name]
        trials = []
        for s in seeds:
            r = await run_trial(Config(seed=s, **regime))
            trials.append(r)
            print(_line(f"{name} seed {s}", r), flush=True)
        out[name] = {"regime": regime, "trials": trials, "summary": summarise(trials)}
        save(f"exp2_main_{tag}" if tag else "exp2_main", out)
    return out


def _entry(trials, **params):
    return {**params, "summary": summarise(trials),
            "farm_value": ci95([t["farm_value"] for t in trials]),
            "benign_in_group_share": [t["benign_in_group_share"] for t in trials],
            "group_z": [t["group_z"] for t in trials]}


# The sweeps are split into three parts so that each can run in its own
# process against its own throwaway Neo4j; each part saves its own file.
SWEEP_PARTS = ("explore", "weight_favours", "intensity_adaptive")


async def sweeps(part: str, seeds=tuple(range(1, 11))) -> dict:
    out: dict[str, list] = {}

    async def block(key, label, base, configs):
        out.setdefault(key, [])
        for params in configs:
            trials = [await run_trial(Config(seed=s, **{**base, **params})) for s in seeds]
            out[key].append(_entry(trials, base=label, **params))
            sm = out[key][-1]["summary"]
            print(f"{label} {params}: find_rings P/R={sm['find_rings']['precision']['mean']}/"
                  f"{sm['find_rings']['recall']['mean']} "
                  f"+policy P/R={sm['find_rings_policy']['precision']['mean']}/"
                  f"{sm['find_rings_policy']['recall']['mean']} "
                  f"+fitted P/R={sm['find_rings_policy_fitted']['precision']['mean']}/"
                  f"{sm['find_rings_policy_fitted']['recall']['mean']} "
                  f"fp {sm['find_rings']['fp']['mean']}->{sm['find_rings_policy']['fp']['mean']}"
                  f"->{sm['find_rings_policy_fitted']['fp']['mean']}",
                  flush=True)
            save(f"exp2_sweeps_{part}", out)

    if part == "explore":
        for label in ("coordinated", "busy"):
            await block("explore", label, REGIMES[label],
                        [{"explore_rate": x} for x in (0.0, 0.05, 0.10, 0.20, 0.40)])
    elif part == "weight_favours":
        for label in ("coordinated", "busy"):
            await block("weight", label, REGIMES[label],
                        [{"social_weight_m": w} for w in (0.0, 1500.0, 3000.0)])
        await block("favours", "favours", ROUTINE,
                    [{"favours_per_member": d} for d in (0, 3, 6, 12, 24)])
    elif part == "intensity_adaptive":
        await block("intensity", "routine", ROUTINE,
                    [{"farm_per_member": f} for f in (2, 4, 8, 12, 24)])
        # The adaptive attacker: a coordinated ring that knows the deployed
        # test and chooses how much to farm. Recall against volume, with the
        # money the ring moved, is where the identifiability limit shows.
        await block("adaptive", "coordinated", COORDINATED,
                    [{"farm_per_member": f} for f in (2, 4, 8, 12, 24)])
    else:
        raise SystemExit(f"unknown sweep part {part!r}; one of {SWEEP_PARTS}")
    return out


if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "main"
    if which == "probe":
        # Calibration only, not a reported result: python -m ... probe key=value ...
        params = {}
        for kv in sys.argv[2:]:
            k, v = kv.split("=")
            field_type = type(getattr(Config(), k))
            params[k] = field_type(v)

        async def _probe():
            r = await run_trial(Config(**params))
            s = r["scores"]
            farms = sum(1 for e in r.get("found", []))
            print(params, "benign_in_group", r["benign_in_group_share"], "rings_found",
                  r["rings_found"], "| find_rings", {k: s["find_rings"][k] for k in
                  ("tp", "fp", "fp_benign_group")}, "| +policy",
                  {k: s["find_rings_policy"][k] for k in ("tp", "fp", "fp_benign_group")},
                  "| ring z", sorted(g["z"] for g in r["group_z"] if g["kind"] == "ring"
                                    and g["z"] is not None),
                  "| benign z>3:", sum(1 for g in r["group_z"] if g["kind"] == "benign"
                                       and g["z"] is not None and g["z"] > 3), farms, flush=True)
        asyncio.run(_probe())
    elif which in ("one", "hard"):
        regime = HARD if which == "hard" else ROUTINE
        r = asyncio.run(run_trial(Config(seed=1, **regime)))
        print({k: v for k, v in r.items() if k not in ("found", "group_z")})
        for f in r["found"]:
            print(f)
        zs = sorted((g["kind"], g["z"]) for g in r["group_z"])
        print(zs)
    elif which == "main":
        if len(sys.argv) > 2:
            # e.g. main routine,busy  -> paper-artifacts/results/exp2_main_routine-busy.json
            names = tuple(sys.argv[2].split(","))
            asyncio.run(main_ablation(regimes=names, tag="-".join(names)))
        else:
            asyncio.run(main_ablation())
    elif which == "quick":
        asyncio.run(main_ablation(seeds=(1,)))
    elif which == "sweeps":
        asyncio.run(sweeps(sys.argv[2]))
    else:
        raise SystemExit(f"unknown mode {which!r}")
