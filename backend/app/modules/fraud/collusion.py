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

# Directed 3-cycles of PAID edges where all three are mutual friends.
#
# `a.id < b.id AND a.id < c.id` keeps one representative per cycle instead of
# all three rotations. The reverse cycle (a→c→b→a) is deliberately NOT deduped
# against this one: money going both ways round a triangle is a stronger
# signal, not a duplicate of the same finding.
FIND_RINGS = """
MATCH (a:User)-[:PAID]->(b:User)-[:PAID]->(c:User)-[:PAID]->(a)
WHERE a.id < b.id AND a.id < c.id
  AND (a)-[:FRIEND]-(b) AND (b)-[:FRIEND]-(c) AND (c)-[:FRIEND]-(a)
// Collapse to the distinct triangle FIRST. Matching all three legs in one
// pattern yields every combination of them, so aggregating there multiplies
// each leg's value by the number of combinations — 4 laps became 64 payments.
// Each leg has to be summed on its own.
WITH DISTINCT a, b, c
CALL (a, b) {
  MATCH (a)-[p:PAID]->(b)
  RETURN sum(coalesce(p.amount, 0.0)) AS v1, count(DISTINCT p.errand_id) AS n1
}
CALL (b, c) {
  MATCH (b)-[p:PAID]->(c)
  RETURN sum(coalesce(p.amount, 0.0)) AS v2, count(DISTINCT p.errand_id) AS n2
}
CALL (c, a) {
  MATCH (c)-[p:PAID]->(a)
  RETURN sum(coalesce(p.amount, 0.0)) AS v3, count(DISTINCT p.errand_id) AS n3
}
WITH a, b, c, v1, v2, v3,
     // Laps = how many complete circuits the money could have made. The
     // narrowest leg is the bottleneck, so that is the honest count.
     CASE WHEN n1 < n2 AND n1 < n3 THEN n1 WHEN n2 < n3 THEN n2 ELSE n3 END AS laps,
     CASE WHEN v1 < v2 AND v1 < v3 THEN v1 WHEN v2 < v3 THEN v2 ELSE v3 END AS min_leg
WHERE laps >= $min_laps AND min_leg >= $min_leg_value
RETURN [a.id, b.id, c.id]       AS members,
       [a.name, b.name, c.name] AS names,
       v1 + v2 + v3             AS total_value,
       laps                     AS laps,
       min_leg                  AS min_leg_value,
       (coalesce(a.closure, 0.0) + coalesce(b.closure, 0.0)
        + coalesce(c.closure, 0.0)) / 3.0 AS closure
ORDER BY total_value DESC
LIMIT 50
"""


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
        )
        logger.info("graph: refreshed payment circulation")
    except Exception:
        logger.warning("graph: circulation refresh failed", exc_info=True)


async def find_rings() -> list[Ring]:
    """Closed money cycles among mutual friends.

    Returns [] when the graph is silent — `run_read` swallows failures by
    design. That is the safe direction here: a graph outage must not manufacture
    accusations, and the worst case is that detection pauses until it recovers.
    """
    rows = await run_read(
        FIND_RINGS, min_laps=MIN_RING_LAPS, min_leg_value=MIN_RING_LEG_VALUE
    )
    rings: list[Ring] = []
    for r in rows:
        try:
            members = tuple(uuid.UUID(m) for m in r["members"] if m)
        except (ValueError, TypeError):
            continue
        if len(members) < MIN_RING_SIZE:
            continue
        rings.append(
            Ring(
                members=members,
                names=tuple(n or "?" for n in (r.get("names") or [])),
                total_value=float(r.get("total_value") or 0.0),
                laps=int(r.get("laps") or 0),
                min_leg_value=float(r.get("min_leg_value") or 0.0),
                closure=float(r.get("closure") or 0.0),
            )
        )
    return rings


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
