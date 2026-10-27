"""Experiment 1: what the closure metric measures, against the clustering coefficient.

Canonical neighbourhood shapes are loaded into the throwaway Neo4j and scored
by the production REFRESH_METRICS query (modules/social/projection.py). The
same quantities are computed exactly in Python as a cross-check, together with
the local clustering coefficient (Watts-Strogatz) and the ego-inclusive variant
of closure that the code comments describe as a bug.

Run: python -m evals.paper.exp1_closure
"""

from __future__ import annotations

import asyncio
import random
from itertools import combinations

from app.modules.social.projection import refresh_graph_metrics
from app.modules.social.service import _closure_penalty
from evals.paper import neo
from evals.paper.common import attach_graph_warning_counter, save, uid


class Builder:
    def __init__(self, seed: int = 7):
        self.n = 0
        self.edges: set[tuple[int, int]] = set()
        self.rng = random.Random(seed)
        self.pool = self.background(300, 6.0)

    def node(self) -> int:
        self.n += 1
        return self.n - 1

    def edge(self, a: int, b: int) -> None:
        if a != b:
            self.edges.add((min(a, b), max(a, b)))

    def background(self, size: int, mean_degree: float) -> list[int]:
        """A random campus the outsiders belong to (Erdos-Renyi)."""
        nodes = [self.node() for _ in range(size)]
        p = mean_degree / (size - 1)
        for a, b in combinations(nodes, 2):
            if self.rng.random() < p:
                self.edge(a, b)
        return nodes

    def social_outsider(self, extra: int) -> int:
        o = self.node()
        for b in self.rng.sample(self.pool, extra):
            self.edge(o, b)
        return o

    def clique(self, k: int) -> list[int]:
        members = [self.node() for _ in range(k)]
        for a, b in combinations(members, 2):
            self.edge(a, b)
        return members


def adjacency(edges):
    adj: dict[int, set[int]] = {}
    for a, b in edges:
        adj.setdefault(a, set()).add(b)
        adj.setdefault(b, set()).add(a)
    return adj


def lcc(adj, u) -> float:
    ns = adj.get(u, set())
    d = len(ns)
    if d < 2:
        return 0.0
    links = sum(1 for a, b in combinations(ns, 2) if b in adj.get(a, set()))
    return 2.0 * links / (d * (d - 1))


def closure_excluding_ego(adj, u) -> float:
    """Python transcription of REFRESH_METRICS (projection.py)."""
    ns = adj.get(u, set())
    if len(ns) < 2:
        return 0.0
    inside_ends = 0
    boundary = 0
    for a in ns:
        for x in adj.get(a, set()):
            if x == u:
                continue
            if x in ns:
                inside_ends += 1
            else:
                boundary += 1
    internal = inside_ends / 2.0
    if internal + boundary == 0:
        return 0.0
    return internal / (internal + boundary)


def closure_including_ego(adj, u) -> float:
    """The variant the code comments warn against: ego counted inside."""
    ns = adj.get(u, set()) | {u}
    internal_ends = 0
    boundary = 0
    for a in ns:
        for x in adj.get(a, set()):
            if x in ns:
                internal_ends += 1
            else:
                boundary += 1
    internal = internal_ends / 2.0
    return internal / (internal + boundary) if internal + boundary else 0.0


def build_cases(b: Builder) -> list[dict]:
    cases = []

    for k in (3, 4, 6, 10):
        m = b.clique(k)
        cases.append({"shape": "sealed clique", "k": k, "ego": m[0]})

    for k in (4, 10):
        m = b.clique(k)
        for v in m:
            b.edge(v, b.node())  # one private friend who knows nobody else
        cases.append({"shape": "clique, one leaf friend each", "k": k, "ego": m[0]})

    for k in (4, 10):
        m = b.clique(k)
        for v in m:
            for _ in range(2):
                b.edge(v, b.social_outsider(5))
        cases.append({"shape": "clique, two sociable friends each", "k": k, "ego": m[0]})

    # Ego's three friends all know each other, but each has a busy life outside.
    ego = b.node()
    tri = [b.node() for _ in range(3)]
    for t in tri:
        b.edge(ego, t)
        for x in b.rng.sample(b.pool, 20):
            b.edge(t, x)
    for x, y in combinations(tri, 2):
        b.edge(x, y)
    cases.append({"shape": "friends form a triangle, each with 20 outside ties", "k": 4,
                  "ego": ego})

    # A sociable hub whose eight friends do not know each other.
    hub = b.node()
    for _ in range(8):
        f = b.node()
        b.edge(hub, f)
        for x in b.rng.sample(b.pool, 4):
            b.edge(f, x)
    cases.append({"shape": "hub, 8 mutually unacquainted friends", "k": 9, "ego": hub})

    # Same hub, but each friend has just one other tie: the case where counting
    # ego's own spokes as internal makes an open star look closed.
    hub2 = b.node()
    for _ in range(8):
        f = b.node()
        b.edge(hub2, f)
        b.edge(f, b.rng.choice(b.pool))
    cases.append({"shape": "hub, 8 unacquainted friends with one tie each", "k": 9,
                  "ego": hub2})

    # A sealed but sparse group: ten people, each friends with four of them.
    ring = [b.node() for _ in range(10)]
    for i, v in enumerate(ring):
        for step in (1, 2):
            b.edge(v, ring[(i + step) % 10])
    cases.append({"shape": "sealed sparse group (10 people, 4 ties each)", "k": 10,
                  "ego": ring[0]})
    return cases


async def main() -> dict:
    neo.assert_throwaway()
    warnings = attach_graph_warning_counter()
    b = Builder()
    cases = build_cases(b)
    adj = adjacency(b.edges)

    await neo.wipe()
    users = [{"id": uid(i), "name": f"s{i}"} for i in range(b.n)]
    friends = [{"a": uid(a), "b": uid(c), "since": None} for a, c in sorted(b.edges)]
    await neo.load(users, friends, [])
    await refresh_graph_metrics()
    metrics = await neo.node_metrics()
    if warnings.count:
        raise RuntimeError(f"graph warnings during run: {warnings.messages[:3]}")

    # Cross-check the transcription against the production query on every node.
    max_diff = max(
        abs(metrics[uid(v)]["closure"] - closure_excluding_ego(adj, v)) for v in range(b.n)
    )

    rows = []
    for c in cases:
        u = c["ego"]
        m = metrics[uid(u)]
        lc = lcc(adj, u)
        rows.append({
            "shape": c["shape"],
            "k": c["k"],
            "degree": m["degree"],
            "clustering": round(lc, 3),
            "closure": round(m["closure"], 3),
            "closure_incl_ego": round(closure_including_ego(adj, u), 3),
            "penalty_from_closure": round(_closure_penalty(m["closure"], m["degree"], 0.0), 3),
            "penalty_if_clustering_used": round(_closure_penalty(lc, m["degree"], 0.0), 3),
        })

    out = {
        "nodes": b.n,
        "edges": len(b.edges),
        "max_abs_diff_cypher_vs_python_closure": max_diff,
        "rows": rows,
    }
    print(f"{b.n} nodes, {len(b.edges)} edges; cypher vs python max diff {max_diff:.2e}")
    for r in rows:
        print(r)
    save("exp1_closure", out)
    return out


if __name__ == "__main__":
    asyncio.run(main())
