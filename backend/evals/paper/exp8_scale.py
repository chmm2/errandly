"""Experiment 8: does the evidence pipeline fit a campus-sized budget?

(a) The production strongly_connected_components (iterative Tarjan) on random
    directed graphs, 10^3 to 10^6 nodes, three out-edges per node.
(b) The production graph jobs on synthetic campuses of 1,200 to 10,000
    students, timed against the throwaway Neo4j: REFRESH_METRICS (closure),
    REFRESH_CIRCULATION, find_rings, and the social_scores query that sits on
    the dispatch path. Each job is run REPEATS times on the loaded graph and
    the median and the min-max range are reported; trust lookups are 50
    calls after 10 discarded warm-up calls.
(c) The acceptance-model fit (policy.fit_acceptance_model) on 1,000 to
    100,000 logged rounds, five repetitions each.

Run: python -m evals.paper.exp8_scale
"""

from __future__ import annotations

import asyncio
import random
import statistics
import time
import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from app.modules.fraud import collusion, policy
from app.modules.social import service as social_service
from app.modules.social.projection import refresh_graph_metrics
from evals.paper import neo
from evals.paper.common import attach_graph_warning_counter, save, uid

REPEATS = 5


def spread(times: list[float], digits: int = 3) -> dict:
    return {"median": round(statistics.median(times), digits),
            "min": round(min(times), digits), "max": round(max(times), digits),
            "repeats": len(times)}


def fit_timing() -> list[dict]:
    out = []
    for rounds in (1_000, 10_000, 100_000):
        rng = random.Random(rounds)
        rows = []
        for _ in range(rounds):
            cands = [{"runner_id": str(uuid.uuid4()), "distance_m": rng.uniform(50, 1500),
                      "hops": rng.choice((1, 2, None, None)), "reputation": 3.5}
                     for _ in range(rng.randint(2, 8))]
            taker = min(cands, key=lambda c: c["distance_m"] + rng.gauss(0, 300))
            rows.append(SimpleNamespace(accepted_runner_id=uuid.UUID(taker["runner_id"]),
                                        candidates=cands))
        times = []
        for _ in range(REPEATS):
            t0 = time.perf_counter()
            policy.fit_acceptance_model(rows)
            times.append(time.perf_counter() - t0)
        out.append({"rounds": rounds, "seconds": spread(times)})
        print(out[-1], flush=True)
    return out


def scc_timing() -> list[dict]:
    out = []
    for n in (1_000, 10_000, 100_000, 1_000_000):
        rng = random.Random(n)
        edges = {i: {rng.randrange(n) for _ in range(3)} - {i} for i in range(n)}
        nodes = set(range(n))
        times = []
        for _ in range(REPEATS):
            t0 = time.perf_counter()
            comps = collusion.strongly_connected_components(nodes, edges)
            times.append(time.perf_counter() - t0)
        out.append({"nodes": n, "edges": sum(len(v) for v in edges.values()),
                    "components_ge2": len(comps), "seconds": spread(times)})
        print(out[-1], flush=True)
    return out


def synthetic_campus(n: int, seed: int = 5):
    """Friendships by block (sampled, not enumerated) and a semester of payments."""
    rng = random.Random(seed)
    block = 50
    edges: set[tuple[int, int]] = set()
    for b in range(0, n, block):
        members = list(range(b, min(n, b + block)))
        for _ in range(int(len(members) * 5 / 2)):
            a, c = rng.sample(members, 2)
            edges.add((min(a, c), max(a, c)))
    for _ in range(n):  # about two friends elsewhere each, counted per endpoint
        a, c = rng.randrange(n), rng.randrange(n)
        if a != c:
            edges.add((min(a, c), max(a, c)))
    adj: dict[int, list[int]] = {}
    for a, c in edges:
        adj.setdefault(a, []).append(c)
        adj.setdefault(c, []).append(a)
    now = datetime.now(UTC)
    pays = []
    eid = 0
    for u in range(n):
        for _ in range(20):
            if adj.get(u) and rng.random() < 0.3:
                v = rng.choice(adj[u])
            else:
                v = rng.randrange(max(0, u - 150), min(n, u + 150))
            if v == u:
                continue
            eid += 1
            pays.append({"src": uid(u), "dst": uid(v), "eid": f"s{eid}",
                         "amount": float(rng.choice((20, 30, 40, 50)) +
                                         (rng.choice((0, 0, 0, 100, 200)))),
                         "at": (now - timedelta(days=rng.uniform(0, 170))).isoformat()})
    return edges, pays


async def neo_timing() -> list[dict]:
    neo.assert_throwaway()
    warnings = attach_graph_warning_counter()
    out = []
    for n in (1_200, 2_500, 5_000, 10_000):
        edges, pays = synthetic_campus(n)
        await neo.wipe()
        t0 = time.perf_counter()
        await neo.load([{"id": uid(i), "name": f"s{i}"} for i in range(n)],
                       [{"a": uid(a), "b": uid(c), "since": None} for a, c in sorted(edges)],
                       pays)
        t_load = time.perf_counter() - t0

        t_metrics, t_circ, t_rings = [], [], []
        for _ in range(REPEATS):
            t1 = time.perf_counter()
            await refresh_graph_metrics()
            t_metrics.append(time.perf_counter() - t1)
            t2 = time.perf_counter()
            await collusion.refresh_circulation()
            t_circ.append(time.perf_counter() - t2)
            t3 = time.perf_counter()
            rings = await collusion.find_rings()
            t_rings.append(time.perf_counter() - t3)

        rng = random.Random(n)
        lat = []
        for _ in range(60):  # 10 warm-up + 50 timed
            r = rng.randrange(n)
            req = uuid.UUID(uid(r))
            # Production never offers a requester their own errand, and Neo4j's
            # shortestPath rejects a path from a node to itself.
            cands = [uuid.UUID(uid(c)) for c in rng.sample([i for i in range(n) if i != r], 5)]
            ts = time.perf_counter()
            await social_service.social_scores(req, cands)
            lat.append((time.perf_counter() - ts) * 1000)
        lat = lat[10:]  # discard warm-up
        if warnings.count:
            raise RuntimeError(f"graph warnings: {warnings.messages[:3]}")
        row = {"students": n, "friend_edges": len(edges), "payments": len(pays),
               "load_s": round(t_load, 1), "refresh_metrics_s": spread(t_metrics, 2),
               "refresh_circulation_s": spread(t_circ, 2), "find_rings_s": spread(t_rings, 2),
               "total_jobs_s_median": round(statistics.median(
                   [a + b + c for a, b, c in zip(t_metrics, t_circ, t_rings, strict=False)]), 2),
               "rings": len(rings),
               "social_scores_ms_p50": round(statistics.median(lat), 1),
               "social_scores_ms_p95": round(sorted(lat)[int(0.95 * len(lat))], 1),
               "social_scores_calls": len(lat)}
        out.append(row)
        print(row, flush=True)
    return out


async def main() -> dict:
    out = {"repeats": REPEATS, "scc": scc_timing(), "fit": fit_timing(),
           "neo4j": await neo_timing()}
    save("exp8_scale", out)
    return out


if __name__ == "__main__":
    asyncio.run(main())
