"""Collusion-ring detection over the `PAID` edges in the social graph.

This is the other half of the closure penalty in `modules/social/service.py`.
That module's own docstring names the limit it cannot pass:

    Structure alone cannot separate a genuine four-person friend group from a
    four-person collusion ring. Both look identically closed. Structure says
    "this group is capable of collusion", never "this group is colluding."

The discriminator is whether **value circulates**. Friends who happen to know
each other still mostly transact with the rest of campus: they order from
strangers, they run for strangers, and money enters and leaves the group. A
ring is the shape where money goes round and comes back — the same rupees
moving between the same few people, with the platform paying a reward on every
lap.

Two signals, deliberately separate:

1. **Circulation** — per user, the share of their platform money that moved
   between them and their own friends. A scalar, refreshed on a timer, stored
   on the node beside `degree` and `closure`, and read by the trust ranker.
   This is a *gradient*: it discounts, it does not accuse.

2. **Closed money cycles** — an actual directed `PAID` cycle whose members are
   all mutual friends. This is not a gradient; it is a specific accusation
   about a specific set of people, so it raises a flag for a human and demands
   far more evidence before it fires.

No GDS. Louvain would be the textbook tool for the community half, but the
plugin downloads at container boot, so installing it makes an offline start
fail the whole stack (see SOCIAL_GRAPH.md §8). Everything here is plain Cypher
over a campus-sized graph.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
import uuid
from dataclasses import dataclass, field

from app.core.graph import run_read, run_write

logger = logging.getLogger(__name__)

# --- circulation ------------------------------------------------------------

# Below this share of internal value, a neighbourhood is behaving like an
# ordinary friend group and circulation contributes nothing. Ordinary students
# DO run errands for their friends, and that must stay unremarkable.
CIRCULATION_KNEE = 0.60

# A user needs at least this much settled value before circulation means
# anything. Someone with two completed errands, both for a friend, reads as
# 100% internal and is simply new.
# How far back the money evidence reaches.
#
# Circulation and ring detection were all-time, which is inconsistent with the
# rest of the system and unfair in a specific way: strikes and flags already
# age out over 30 days, so the PENALTY decayed while the EVIDENCE never did. A
# ring that circulated eight months ago and stopped stayed flagged forever, and
# a user whose first errands happened to be with friends carried that ratio for
# the rest of their time on campus with no way back.
#
# Two semesters. Long enough that a genuine pattern cannot hide by pausing for
# a few weeks, short enough that behaviour a year old stops being treated as
# current conduct. Edges with no timestamp are counted rather than dropped:
# older rows predate the field, and silently discarding evidence would be the
# more dangerous default.
MONEY_WINDOW_DAYS = 180

MIN_CIRCULATION_VALUE = 300.0
MIN_CIRCULATION_TXNS = 4

# --- rings ------------------------------------------------------------------

# A reciprocating pair is not a ring. Two friends alternating who fetches lunch
# is the most ordinary thing on this platform, and flagging it would bury the
# real signal in noise. Three is where "taking turns" starts to look designed.
MIN_RING_SIZE = 3

# Every leg of the cycle must carry real money, and the loop must have gone
# round more than once. A single coincidental A→B→C→A over a semester is not
# evidence of anything.
MIN_RING_LEG_VALUE = 150.0
MIN_RING_LAPS = 2


@dataclass(frozen=True)
class Ring:
    """One closed money cycle among mutual friends."""

    members: tuple[uuid.UUID, ...]
    names: tuple[str, ...] = field(default=())
    total_value: float = 0.0
    laps: int = 0
    min_leg_value: float = 0.0
    # Mean closure of the members — how sealed off the group is structurally.
    closure: float = 0.0

    @property
    def size(self) -> int:
        return len(self.members)


def circulation_penalty(circulation: float) -> float:
    """Extra discount justified by money-flow evidence, in [0, 1].

    Ramps from the knee rather than switching on, so a neighbourhood that
    drifts a little above ordinary is nudged rather than condemned. The caller
    decides what to do with it; this only says how strong the evidence is.
    """
    if circulation <= CIRCULATION_KNEE:
        return 0.0
    return min(1.0, (circulation - CIRCULATION_KNEE) / (1.0 - CIRCULATION_KNEE))


# For each user: what share of the value they moved on this platform stayed
# between them and their own friends.
#
# Both directions count. A ring launders reward money in both roles — today's
# requester is tomorrow's runner — so measuring only outgoing payments would
# miss half of every lap.
REFRESH_CIRCULATION = """
MATCH (u:User)
OPTIONAL MATCH (u)-[p:PAID]-(other:User)
WHERE p IS NULL OR p.at IS NULL OR datetime(p.at) >= datetime($since)
WITH u, other, p
WITH u,
     sum(coalesce(p.amount, 0.0)) AS total_value,
     count(p) AS total_txns,
     sum(CASE WHEN p IS NOT NULL AND (u)-[:FRIEND]-(other)
              THEN coalesce(p.amount, 0.0) ELSE 0.0 END) AS internal_value,
     sum(CASE WHEN p IS NOT NULL AND (u)-[:FRIEND]-(other) THEN 1 ELSE 0 END) AS internal_txns
SET u.paid_value     = total_value,
    u.paid_txns      = total_txns,
    u.internal_value = internal_value,
    // Below the evidence floor circulation is 0, not "unknown" — the ranker
    // reads this directly and a null would quietly become a penalty.
    u.circulation    = CASE
        WHEN total_value < $min_value OR total_txns < $min_txns THEN 0.0
        WHEN total_value = 0 THEN 0.0
        ELSE internal_value / total_value END
"""

# Every PAID edge between two mutual friends, collapsed to one row per ordered
# pair. Cycle-finding happens in Python over this edge list rather than in
# Cypher, because a fixed-length pattern can only ever find fixed-length rings
# and the cost of evading one is a single extra member. See find_rings.
FRIEND_PAYMENT_EDGES = """
MATCH (a:User)-[p:PAID]->(b:User)
WHERE (a)-[:FRIEND]-(b)
  AND (p.at IS NULL OR datetime(p.at) >= datetime($since))
RETURN a.id AS src, b.id AS dst,
       a.name AS src_name, b.name AS dst_name,
       sum(coalesce(p.amount, 0.0))    AS value,
       count(DISTINCT p.errand_id)     AS txns,
       coalesce(a.closure, 0.0)        AS src_closure
"""

# The previous implementation matched a hard-coded three-hop Cypher pattern.
# It is in git history if the contrast is ever useful; see find_rings for why
# a fixed-length pattern cannot work here.


def strongly_connected_components(
    nodes: set[str], edges: dict[str, set[str]]
) -> list[set[str]]:
    """Tarjan's algorithm. Every component of size >= 2 contains a cycle.

    Iterative rather than recursive: the recursive form is shorter, but its
    depth is the length of the longest path in the graph, and a campus graph
    can exceed Python's default limit on a bad day. A detector that raises
    RecursionError instead of finding a ring is worse than one that is slightly
    longer to read.
    """
    index: dict[str, int] = {}
    low: dict[str, int] = {}
    on_stack: set[str] = set()
    stack: list[str] = []
    result: list[set[str]] = []
    counter = 0

    for root in nodes:
        if root in index:
            continue
        # (node, iterator over its successors)
        work: list[tuple[str, list[str]]] = [(root, list(edges.get(root, ())))]
        index[root] = low[root] = counter
        counter += 1
        stack.append(root)
        on_stack.add(root)

        while work:
            node, successors = work[-1]
            if successors:
                nxt = successors.pop()
                if nxt not in index:
                    index[nxt] = low[nxt] = counter
                    counter += 1
                    stack.append(nxt)
                    on_stack.add(nxt)
                    work.append((nxt, list(edges.get(nxt, ()))))
                elif nxt in on_stack:
                    low[node] = min(low[node], index[nxt])
            else:
                work.pop()
                if work:
                    parent = work[-1][0]
                    low[parent] = min(low[parent], low[node])
                if low[node] == index[node]:
                    component: set[str] = set()
                    while True:
                        member = stack.pop()
                        on_stack.discard(member)
                        component.add(member)
                        if member == node:
                            break
                    if len(component) > 1:
                        result.append(component)
    return result


def _window_start() -> str:
    """ISO timestamp for the start of the money-evidence window."""
    return (datetime.now(UTC) - timedelta(days=MONEY_WINDOW_DAYS)).isoformat()


async def refresh_circulation() -> None:
    """Recompute per-user circulation. Timer job, alongside the graph metrics.

    Failure is logged, not raised: a stale circulation figure degrades trust
    ranking slightly, while a raised exception would take down the scheduler
    that also runs offer broadening and errand expiry.
    """
    try:
        await run_write(
            REFRESH_CIRCULATION,
            min_value=MIN_CIRCULATION_VALUE,
            min_txns=MIN_CIRCULATION_TXNS,
            since=_window_start(),
        )
        logger.info("graph: refreshed payment circulation")
    except Exception:
        logger.warning("graph: circulation refresh failed", exc_info=True)


async def find_rings() -> list[Ring]:
    """Closed money cycles among mutual friends, of any size.

    Previously this matched a hard-coded three-hop pattern, which made the cost
    of evading the platform's strongest fraud signal exactly one extra member:
    a four-person loop with no internal triangle produced nothing. That matters
    more since rating provenance began counting distinct raters, because the
    cheapest way to defeat *that* is to recruit breadth — which requires a
    larger ring, landing the attacker precisely in the old blind spot.

    Method: keep only payment edges between mutual friends that individually
    carry enough money and enough separate errands, then look for strongly
    connected components in what remains. Every component of size >= 2 contains
    a cycle by definition, so this finds loops of any length without
    enumerating paths.

    Filtering edges BEFORE the search rather than measuring afterwards is the
    part that matters. Taking a minimum across a whole component would let a
    ring hide behind one deliberate ₹1 payment between two of its members,
    dragging the bottleneck under the threshold. An edge that does not qualify
    is simply not part of the ring.

    Returns [] when the graph is silent — `run_read` swallows failures by
    design. That is the safe direction: an outage must not manufacture
    accusations.
    """
    rows = await run_read(FRIEND_PAYMENT_EDGES, since=_window_start())
    if not rows:
        return []

    nodes: set[str] = set()
    adjacency: dict[str, set[str]] = {}
    edge_value: dict[tuple[str, str], float] = {}
    edge_txns: dict[tuple[str, str], int] = {}
    names: dict[str, str] = {}
    closures: dict[str, float] = {}

    for r in rows:
        src, dst = r.get("src"), r.get("dst")
        if not src or not dst or src == dst:
            continue
        value = float(r.get("value") or 0.0)
        txns = int(r.get("txns") or 0)
        # An edge only counts toward a ring if it is substantial on its own.
        if value < MIN_RING_LEG_VALUE or txns < MIN_RING_LAPS:
            continue
        nodes.update((src, dst))
        adjacency.setdefault(src, set()).add(dst)
        edge_value[(src, dst)] = value
        edge_txns[(src, dst)] = txns
        names[src] = r.get("src_name") or "?"
        names[dst] = r.get("dst_name") or "?"
        closures[src] = float(r.get("src_closure") or 0.0)

    rings: list[Ring] = []
    for component in strongly_connected_components(nodes, adjacency):
        if len(component) < MIN_RING_SIZE:
            continue
        internal = [
            (a, b)
            for (a, b) in edge_value
            if a in component and b in component
        ]
        if not internal:
            continue
        try:
            members = tuple(uuid.UUID(m) for m in sorted(component))
        except (ValueError, TypeError):
            continue

        member_closures = [closures.get(m, 0.0) for m in component]
        rings.append(
            Ring(
                members=members,
                names=tuple(names.get(m, "?") for m in sorted(component)),
                total_value=sum(edge_value[e] for e in internal),
                # The narrowest leg is the bottleneck: money cannot go round
                # more times than the thinnest hop allows.
                laps=min(edge_txns[e] for e in internal),
                min_leg_value=min(edge_value[e] for e in internal),
                closure=(
                    sum(member_closures) / len(member_closures)
                    if member_closures
                    else 0.0
                ),
            )
        )

    rings.sort(key=lambda r: r.total_value, reverse=True)
    return rings[:50]


async def circulation_for(user_ids: list[uuid.UUID]) -> dict[uuid.UUID, float]:
    """Circulation per user, for explaining a flag in the admin console."""
    if not user_ids:
        return {}
    rows = await run_read(
        """
        UNWIND $ids AS uid
        MATCH (u:User {id: uid})
        RETURN u.id AS id,
               coalesce(u.circulation, 0.0)   AS circulation,
               coalesce(u.paid_value, 0.0)    AS paid_value,
               coalesce(u.internal_value, 0.0) AS internal_value
        """,
        ids=[str(u) for u in user_ids],
    )
    return {uuid.UUID(r["id"]): float(r["circulation"] or 0.0) for r in rows}
