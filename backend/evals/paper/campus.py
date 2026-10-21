"""A simulated campus: friendships, geography, and a semester of errands.

Used by the collusion experiment (exp2) and the dispatch experiment (exp6).

What is simulated, and what is not
----------------------------------
Simulated: who is friends with whom (a stochastic block model over hostel
blocks, with planted close-knit groups), where students live, who is online
when an errand is posted, how long an offered runner takes to respond, and
whether they accept.

Not simulated: the dispatch rules themselves. Ranking (`_rank_with_scores`,
`_terms_for`), the exploration coin (`should_explore`), the trust formula
(`HOP_DECAY`, `_closure_penalty`, `_direct_penalty`), the tier schedule
(`SOCIAL_TIERS`, `SCHEDULER_INTERVAL`, `BROADEN_FANOUT`) and the first-offer
fan-out (`OFFER_FANOUT`, `OFFER_RADIUS_M`, `SOCIAL_TIER_1_HOPS`) are imported
from the production modules and called as they are.

Two places where the simulator has to stand in for storage: social scores are
computed from an exact hop table instead of a Neo4j shortestPath query, and
circulation is refreshed every 30 simulated days with a transcription of
REFRESH_CIRCULATION. Both transcriptions are checked against the production
Cypher at the end of every trial (see exp2).
"""

from __future__ import annotations

import math
import random
import uuid
from array import array
from collections import deque
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from app.core.config import settings
from app.modules.errands import service as errands_service
from app.modules.fraud import collusion
from app.modules.social import service as social_service
from app.workers.consumers import BROADEN_FANOUT, SCHEDULER_INTERVAL, SOCIAL_TIERS
from evals.paper.common import uid

DAY = 86400.0
UNREACHED = 255


@dataclass(frozen=True)
class Config:
    seed: int = 1
    # --- the friendship graph -------------------------------------------
    n_blocks: int = 24
    block_size: int = 50
    p_in: float = 0.10       # ~4.9 friends inside one's own hostel block
    p_out: float = 0.0015    # ~1.7 friends elsewhere on campus
    # Close-knit honest groups (roommates, project teams) and collusion rings.
    # Both are planted as cliques inside one hostel block, so the two are
    # structurally identical by construction.
    benign_sizes: tuple = (3,) * 8 + (4,) * 8 + (5,) * 6 + (6,) * 4 + (8,) * 2
    ring_sizes: tuple = (3, 4, 5, 6, 8)
    # --- geography --------------------------------------------------------
    grid_cols: int = 6
    spacing_m: float = 350.0
    home_jitter_m: float = 60.0
    online_frac: float = 0.12
    roam_m: float = 250.0
    # --- demand -----------------------------------------------------------
    days: int = 180
    post_rate: float = 0.12            # errands per student per day
    rewards: tuple = (20, 25, 30, 40, 50)
    collect_prob: float = 0.30
    collect_lo: int = 50
    collect_hi: int = 400
    expiry_s: float = 1800.0           # ErrandCreate.wait_minutes default (30)
    # --- honest runner behaviour (assumed, not measured) -------------------
    base_accept: float = 0.5
    friend_affinity: float = 1.5       # how much likelier a friend says yes
    accept_scale_m: float = 2000.0
    latency_median_s: float = 20.0
    latency_sigma: float = 0.8
    # Honest favours: errands an honest group member posts meaning a particular
    # friend to take them ("grab my parcel on your way back"). Deliberate
    # in-group routing with nothing dishonest about it, and the hardest case
    # for every detector here. 0 = friends only meet through the router.
    favours_per_member: int = 0
    favour_take_prob: float = 0.9
    favour_latency_lo: float = 10.0
    favour_latency_hi: float = 60.0
    # --- collusion rings ----------------------------------------------------
    farm_per_member: int = 12          # extra in-ring errands per member per semester
    farm_reward_lo: int = 10
    farm_reward_hi: int = 20
    farm_next_prob: float = 0.8        # share taken by the next member in the loop
    ring_latency_lo: float = 3.0
    ring_latency_hi: float = 15.0
    # "naive": farm whenever. "stealth": only post a farming errand when the
    # partner is online and among the runners the router itself would offer it
    # to first, so that every farmed round looks like the router's own doing.
    ring_mode: str = "naive"
    stealth_attempts_factor: int = 1
    # --- the platform's own knobs -----------------------------------------
    social_weight_m: float = errands_service.SOCIAL_WEIGHT_M
    explore_rate: float = settings.offer_explore_rate
    circulation_refresh_days: int = 30
    dispatch: str = "staged"           # "staged" (production) | "broadcast" | "sequential"
    # True mirrors the fixed scheduler; False reproduces the original rule,
    # under which an errand that first went out unrestricted was never widened.
    widen_open_offers: bool = True


class Campus:
    """Static structure for one seed: friendships, homes, planted groups."""

    def __init__(self, cfg: Config):
        rng = random.Random(cfg.seed * 7919 + 17)
        self.cfg = cfg
        n = cfg.n_blocks * cfg.block_size
        self.n = n
        self.block = [i // cfg.block_size for i in range(n)]
        centre = [
            ((b % cfg.grid_cols) * cfg.spacing_m, (b // cfg.grid_cols) * cfg.spacing_m)
            for b in range(cfg.n_blocks)
        ]
        self.home = [
            (
                centre[self.block[i]][0] + rng.gauss(0, cfg.home_jitter_m),
                centre[self.block[i]][1] + rng.gauss(0, cfg.home_jitter_m),
            )
            for i in range(n)
        ]
        self.adj: list[set[int]] = [set() for _ in range(n)]
        for i in range(n):
            bi = self.block[i]
            for j in range(i + 1, n):
                p = cfg.p_in if self.block[j] == bi else cfg.p_out
                if rng.random() < p:
                    self.adj[i].add(j)
                    self.adj[j].add(i)

        # Planted groups. kind[i] is "ring", "benign" or None.
        self.kind: list[str | None] = [None] * n
        self.group_of: list[int] = [-1] * n
        self.groups: list[dict] = []
        free_by_block = {b: list(range(b * cfg.block_size, (b + 1) * cfg.block_size))
                         for b in range(cfg.n_blocks)}
        for b in free_by_block.values():
            rng.shuffle(b)
        plan = [("ring", k) for k in cfg.ring_sizes] + [("benign", k) for k in cfg.benign_sizes]
        rng.shuffle(plan)
        for gid, (kind, k) in enumerate(plan):
            blocks = [b for b, free in free_by_block.items() if len(free) >= k]
            b = rng.choice(blocks)
            members = [free_by_block[b].pop() for _ in range(k)]
            for a in members:
                for c in members:
                    if a != c:
                        self.adj[a].add(c)
                self.kind[a] = kind
                self.group_of[a] = gid
            self.groups.append({"id": gid, "kind": kind, "members": members})

        self.degree = [len(a) for a in self.adj]
        self.edges = sorted((a, b) for a in range(n) for b in self.adj[a] if a < b)
        self._bfs_all()
        self.closure = [self._closure(u) for u in range(n)]

    # -- structure -----------------------------------------------------------

    def _bfs_all(self) -> None:
        """Exact hop distances (capped at social_max_hops) and first hops."""
        n = self.n
        cap = settings.social_max_hops
        self.hops: list[bytearray] = []
        self.first: list[array] = []
        for s in range(n):
            dist = bytearray([UNREACHED]) * n
            first = array("h", [-1]) * n
            dist[s] = 0
            q = deque()
            for v in self.adj[s]:
                dist[v] = 1
                first[v] = v
                q.append(v)
            while q:
                x = q.popleft()
                dx = dist[x]
                if dx >= cap:
                    continue
                fx = first[x]
                for y in self.adj[x]:
                    if dist[y] == UNREACHED:
                        dist[y] = dx + 1
                        first[y] = fx
                        q.append(y)
            self.hops.append(dist)
            self.first.append(first)

    def _closure(self, u: int) -> float:
        """Transcription of REFRESH_METRICS; checked against the Cypher in exp1/exp2."""
        ns = self.adj[u]
        if len(ns) < 2:
            return 0.0
        inside_ends = boundary = 0
        for a in ns:
            for x in self.adj[a]:
                if x == u:
                    continue
                if x in ns:
                    inside_ends += 1
                else:
                    boundary += 1
        internal = inside_ends / 2.0
        return internal / (internal + boundary) if internal + boundary else 0.0


class Semester:
    """One simulated semester of errands on a campus, under one configuration."""

    def __init__(self, campus: Campus, cfg: Config):
        self.c = campus
        self.cfg = cfg
        # One stream for the world (who posts when, who is online, where), shared
        # by every dispatch policy so that policies are compared on the same
        # semester. Runner decisions get their own per-(errand, runner) streams.
        self.rng = random.Random(cfg.seed * 104729 + 3)
        self.now = datetime.now(UTC)
        self.base = self.now - timedelta(days=cfg.days - 0.1)
        self.circulation = [0.0] * campus.n
        self.payments: list[dict] = []
        self.offer_logs: list[SimpleNamespace] = []
        self.errands: list[dict] = []
        self._paid_value = [0.0] * campus.n
        self._paid_txns = [0] * campus.n
        self._internal_value = [0.0] * campus.n

    # -- production pieces, called as they are --------------------------------

    def scores(self, req: int, cands: list[int]) -> dict:
        """Shape of social_service.social_scores(), from the exact hop table."""
        out = {}
        hrow = self.c.hops[req]
        frow = self.c.first[req]
        for cand in cands:
            h = hrow[cand]
            if h == UNREACHED or h == 0:
                continue
            base = social_service.HOP_DECAY ** (h - 1)
            if h == 1:
                pen = social_service._direct_penalty(
                    self.c.closure[cand], self.c.degree[cand], self.circulation[cand]
                )
            else:
                v = frow[cand]
                pen = social_service._closure_penalty(
                    self.c.closure[v], self.c.degree[v], self.circulation[v]
                )
            out[uid(cand)] = {"hops": h, "trust": round(base * (1.0 - pen) * 1.0, 4)}
        return out

    def rank(self, nearby: list[tuple[str, float]], scores: dict | None) -> list:
        return errands_service._rank_with_scores(nearby, scores, {}, None)

    def log_round(self, req: int, ranked, scores, exploring: bool, t: float):
        row = SimpleNamespace(
            requester_id=uuid.UUID(uid(req)),
            accepted_runner_id=None,
            exploring=exploring,
            created_at=self.base + timedelta(seconds=t),
            candidates=[
                {
                    **errands_service._terms_for(
                        rid, dist, scores, {}, None, apply_trust=not exploring
                    ),
                    "rank": i,
                }
                for i, (rid, dist) in enumerate(ranked)
            ],
        )
        self.offer_logs.append(row)
        return row

    # -- the semester ----------------------------------------------------------

    def run(self) -> None:
        cfg, c, rng = self.cfg, self.c, self.rng
        errands_service.SOCIAL_WEIGHT_M = cfg.social_weight_m
        settings.offer_explore_rate = cfg.explore_rate
        random.seed(cfg.seed * 31 + 5)  # should_explore() draws from the module RNG

        events = []
        horizon = cfg.days * DAY
        for i in range(c.n):
            k = self._poisson(cfg.post_rate * cfg.days)
            for _ in range(k):
                events.append((rng.uniform(0, horizon), i, "normal", None))
        attempts = cfg.stealth_attempts_factor if cfg.ring_mode == "stealth" else 1
        for g in c.groups:
            m = g["members"]
            if g["kind"] == "ring":
                for pos, i in enumerate(m):
                    nxt = m[(pos + 1) % len(m)]
                    for _ in range(cfg.farm_per_member * attempts):
                        if rng.random() < cfg.farm_next_prob:
                            partner = nxt
                        else:
                            partner = rng.choice([x for x in m if x != i])
                        events.append((rng.uniform(0, horizon), i, "farm", partner))
            elif g["kind"] == "benign" and cfg.favours_per_member:
                for i in m:
                    for _ in range(cfg.favours_per_member):
                        partner = rng.choice([x for x in m if x != i])
                        events.append((rng.uniform(0, horizon), i, "favour", partner))
        events.sort(key=lambda e: e[0])

        self.farmed = [0] * c.n
        next_refresh = cfg.circulation_refresh_days * DAY
        for eid, (t, req, kind, partner) in enumerate(events):
            if t >= next_refresh:
                self._refresh_circulation()
                next_refresh += cfg.circulation_refresh_days * DAY
            if kind == "farm" and self.farmed[req] >= cfg.farm_per_member:
                continue
            self._one_errand(eid, t, req, kind, partner)

    def _poisson(self, lam: float) -> int:
        # Knuth; lam is ~20 here, so this is cheap enough.
        L, k, p = math.exp(-lam), 0, 1.0
        while True:
            p *= self.rng.random()
            if p <= L:
                return k
            k += 1

    def _refresh_circulation(self) -> None:
        """REFRESH_CIRCULATION transcribed: share of a user's settled value that
        moved between them and their own friends, zero below the evidence floor."""
        for u in range(self.c.n):
            tv, tx = self._paid_value[u], self._paid_txns[u]
            if tv < collusion.MIN_CIRCULATION_VALUE or tx < collusion.MIN_CIRCULATION_TXNS:
                self.circulation[u] = 0.0
            else:
                self.circulation[u] = self._internal_value[u] / tv if tv else 0.0

    def _one_errand(self, eid: int, t: float, req: int, kind: str, partner: int | None):
        cfg, c, rng = self.cfg, self.c, self.rng
        drop = c.home[req]
        if kind == "farm":
            reward = rng.randint(cfg.farm_reward_lo, cfg.farm_reward_hi)
            collect = 0
        else:
            reward = rng.choice(cfg.rewards)
            collect = (
                rng.randint(cfg.collect_lo // 10, cfg.collect_hi // 10) * 10
                if rng.random() < cfg.collect_prob
                else 0
            )

        online = []
        for i in rng.sample(range(c.n), round(cfg.online_frac * c.n)):
            if i == req:
                continue
            hx, hy = c.home[i]
            x = hx + rng.gauss(0, cfg.roam_m)
            y = hy + rng.gauss(0, cfg.roam_m)
            online.append((math.hypot(x - drop[0], y - drop[1]), i))
        online.sort()

        def nearest(radius: float, limit: int) -> list[int]:
            return [i for d, i in online if d <= radius][:limit]

        dist_of = {i: d for d, i in online}

        if kind == "farm" and cfg.ring_mode == "stealth":
            # A coordinated ring does not wait for luck. The partner goes online
            # and walks over before the errand is posted, so the router itself
            # puts them first in line: nearest runner, a direct friend, inside
            # the tier-1 social radius. Every farmed round then reads, in the
            # offer log, as the router's own preference.
            online = [(d, i) for d, i in online if i != partner]
            online.append((rng.uniform(30.0, 150.0), partner))
            online.sort()
            dist_of = {i: d for d, i in online}
        offers: dict[int, float] = {}   # runner -> time first offered
        last_round = None
        logged: list[bool] = []         # exploring flag of each logged round
        first_tier = None

        def offer(cands_idx: list[int], max_hops: int | None, at: float, log: bool):
            nonlocal last_round
            nearby = [(uid(i), dist_of[i]) for i in cands_idx]
            if not nearby:
                return 0
            sc = self.scores(req, cands_idx)
            exploring = errands_service.should_explore() if log else False
            ranked = self.rank(nearby, None if exploring else sc)
            if max_hops is not None and not exploring:
                ranked = [(r, d) for r, d in ranked if sc.get(r, {}).get("hops", 99) <= max_hops]
                if not ranked:
                    return 0
            if log:
                last_round = self.log_round(req, ranked, sc, exploring, at)
                logged.append(exploring)
            for r, _ in ranked:
                ri = int(uuid.UUID(r).int) - 1
                offers.setdefault(ri, at)
            return len(ranked)

        # The scheduler sweeps every SCHEDULER_INTERVAL seconds and fires at most
        # one tier per sweep, so each escalation waits for the first sweep after
        # its threshold. Drawn here so every policy sees the same phase.
        phase = rng.uniform(0, SCHEDULER_INTERVAL)

        def escalate(tiers, ignore_hops: bool) -> None:
            sweep = phase
            for after_s, _tier, hops, radius_m in tiers:
                while sweep < after_s:
                    sweep += SCHEDULER_INTERVAL
                offer(nearest(radius_m, BROADEN_FANOUT), None if ignore_hops else hops,
                      sweep, log=False)
                sweep += SCHEDULER_INTERVAL

        if cfg.dispatch == "staged":
            n1 = offer(nearest(errands_service.OFFER_RADIUS_M, errands_service.OFFER_FANOUT),
                       errands_service.SOCIAL_TIER_1_HOPS, 0.0, log=True)
            first_tier = 1 if n1 else None
            if not n1:
                n0 = offer(nearest(errands_service.OFFER_RADIUS_M, errands_service.OFFER_FANOUT),
                           None, 0.0, log=True)
                first_tier = 0 if n0 else None
            if first_tier != 0:
                escalate(SOCIAL_TIERS, ignore_hops=False)
            elif cfg.widen_open_offers:
                # Mirrors broaden_stale_offers after the review fix: an errand
                # that went out unrestricted still gets the radius widening.
                escalate([t for t in SOCIAL_TIERS if t[2] is None], ignore_hops=False)
        elif cfg.dispatch == "broadcast":
            # Ranked by trust but sent to everyone at once, so only the ordering
            # carries the social preference. Same radius escalation, no hop gates.
            n0 = offer(nearest(errands_service.OFFER_RADIUS_M, errands_service.OFFER_FANOUT),
                       None, 0.0, log=True)
            first_tier = 0 if n0 else None
            escalate(SOCIAL_TIERS[1:], ignore_hops=True)
        elif cfg.dispatch == "sequential":
            # One runner at a time in rank order, 30 s each: strongest preference,
            # slowest service. A common alternative to staging, for comparison.
            nearby_idx = nearest(errands_service.OFFER_RADIUS_M, BROADEN_FANOUT)
            nearby = [(uid(i), dist_of[i]) for i in nearby_idx]
            sc = self.scores(req, nearby_idx)
            ranked = self.rank(nearby, sc)
            last_round = self.log_round(req, ranked, sc, False, 0.0)
            logged.append(False)
            for pos, (r, _) in enumerate(ranked):
                offers.setdefault(int(uuid.UUID(r).int) - 1, 30.0 * pos)
        else:
            raise ValueError(cfg.dispatch)

        # Who accepts, and when. Each offered runner decides once, from a stream
        # keyed on (seed, errand, runner): the same runner gives the same answer
        # after the same delay whichever policy offered it to them, so policies
        # differ only in WHEN each runner is told.
        best_t, winner = math.inf, None
        for ri, t_off in offers.items():
            d = random.Random((cfg.seed << 42) ^ (eid << 13) ^ ri)
            h = c.hops[req][ri]
            p = cfg.base_accept * math.exp(-dist_of[ri] / cfg.accept_scale_m)
            if h == 1:
                p *= cfg.friend_affinity
            willing = d.random() < min(0.95, p)
            lat = cfg.latency_median_s * math.exp(d.gauss(0, cfg.latency_sigma))
            if willing and t_off + lat < best_t:
                best_t, winner = t_off + lat, ri
        if kind == "farm":
            # The partner takes it from the feed straight away; an honest runner
            # only wins if they happen to be faster.
            d = random.Random((cfg.seed << 42) ^ (eid << 13) ^ 8191)
            lat = d.uniform(cfg.ring_latency_lo, cfg.ring_latency_hi)
            if lat < best_t:
                best_t, winner = lat, partner
            self.farmed[req] += 1
        elif kind == "favour":
            d = random.Random((cfg.seed << 42) ^ (eid << 13) ^ 8190)
            if d.random() < cfg.favour_take_prob:
                lat = d.uniform(cfg.favour_latency_lo, cfg.favour_latency_hi)
                if lat < best_t:
                    best_t, winner = lat, partner

        record = {
            "eid": eid, "t": t, "req": req, "kind": kind, "winner": None,
            "wait_s": None, "first_tier": first_tier,
            "winner_hops": None, "reward": reward, "collect": collect,
            "exploring": bool(logged and logged[-1]),
        }
        if winner is not None and best_t <= cfg.expiry_s:
            record["winner"] = winner
            record["wait_s"] = best_t
            record["winner_hops"] = c.hops[req][winner]
            if last_round is not None:
                last_round.accepted_runner_id = uuid.UUID(uid(winner))
            amount = float(reward + collect)
            self.payments.append({
                "src": uid(req), "dst": uid(winner), "eid": f"e{eid}", "amount": amount,
                "at": (self.base + timedelta(seconds=t)).isoformat(),
            })
            for u, other in ((req, winner), (winner, req)):
                self._paid_value[u] += amount
                self._paid_txns[u] += 1
                if other in c.adj[u]:
                    self._internal_value[u] += amount
        self.errands.append(record)
