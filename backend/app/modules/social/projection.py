"""Projects friendship and settlement events into the Neo4j read model.

Runs as its own Kafka consumer group, so a graph outage never blocks
notifications, analytics or settlement — those groups keep their own offsets
and are unaffected. Writes raise rather than swallow, so an event that fails to
project is not marked processed and gets another attempt on redelivery.
"""

import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.graph import run_write
from app.modules.auth.models import User

logger = logging.getLogger(__name__)

# MERGE, not CREATE: at-least-once delivery means every one of these can arrive
# twice, and the projection has to be idempotent for that to be harmless.
UPSERT_USER = """
MERGE (u:User {id: $id})
SET u.name = $name
"""

LINK_FRIENDS = """
MATCH (a:User {id: $a}), (b:User {id: $b})
MERGE (a)-[r:FRIEND]-(b)
ON CREATE SET r.since = $at
WITH a, b
CALL {
  WITH a MATCH (a)-[:FRIEND]-(n) WITH a, count(DISTINCT n) AS d SET a.degree = d
}
CALL {
  WITH b MATCH (b)-[:FRIEND]-(n) WITH b, count(DISTINCT n) AS d SET b.degree = d
}
"""

UNLINK_FRIENDS = """
MATCH (a:User {id: $a})-[r:FRIEND]-(b:User {id: $b})
DELETE r
WITH a, b
CALL {
  WITH a OPTIONAL MATCH (a)-[:FRIEND]-(n) WITH a, count(DISTINCT n) AS d SET a.degree = d
}
CALL {
  WITH b OPTIONAL MATCH (b)-[:FRIEND]-(n) WITH b, count(DISTINCT n) AS d SET b.degree = d
}
"""

# Money flow, kept as its own edge type. Nothing reads these yet; they exist so
# the fraud work can ask "does value circulate inside this cluster?" without a
# backfill. Direction is requester → runner.
RECORD_PAYMENT = """
MATCH (a:User {id: $from_id}), (b:User {id: $to_id})
MERGE (a)-[p:PAID {errand_id: $errand_id}]->(b)
ON CREATE SET p.amount = $amount, p.at = $at
"""


async def _upsert_user(db: AsyncSession, user_id: str) -> None:
    """Mirror a user into the graph. Names come from Postgres because the event
    payload deliberately carries ids only — a renamed student should not need
    every historical event rewritten."""
    user = await db.get(User, uuid.UUID(user_id))
    await run_write(UPSERT_USER, id=user_id, name=user.display_name if user else None)


async def handle_social(db: AsyncSession, event: dict) -> None:
    kind = event["event_type"]
    payload = event.get("payload") or {}

    if kind == "FriendshipAccepted":
        a, b = payload["user_a"], payload["user_b"]
        await _upsert_user(db, a)
        await _upsert_user(db, b)
        await run_write(LINK_FRIENDS, a=a, b=b, at=payload.get("at"))
        logger.info("graph: linked %s <-> %s", a[:8], b[:8])

    elif kind == "FriendshipRemoved":
        a, b = payload["user_a"], payload["user_b"]
        await run_write(UNLINK_FRIENDS, a=a, b=b)
        logger.info("graph: unlinked %s <-> %s", a[:8], b[:8])

    elif kind == "ORDER_COMPLETED":
        # Value actually changed hands. This is the same event settlement-service
        # pays out on, so a PAID edge exists for exactly the transactions the
        # ledger recorded — see handle_settlement in workers/consumers.py.
        #
        # Nothing reads these yet. They exist so collusion detection can ask
        # "does value circulate inside this cluster?" without a backfill.
        req, run = payload.get("requester_id"), payload.get("runner_id")
        if req and run:
            await _upsert_user(db, req)
            await _upsert_user(db, run)
            await run_write(
                RECORD_PAYMENT,
                from_id=req,
                to_id=run,
                errand_id=str(payload.get("errand_id") or event.get("aggregate_id")),
                # What the requester parted with: the runner's fee plus the cash
                # handed over. items_total is deliberately excluded — it is not
                # settled through the platform (see PaymentSummary on mobile).
                amount=float(payload.get("reward") or 0)
                + float(payload.get("collect_amount") or 0),
                at=payload.get("at"),
            )


# Local clustering coefficient, recomputed on a timer rather than per event:
# one friendship changes the coefficient of everyone in both neighbourhoods, so
# doing it inline would turn a single accept into an unbounded write.
REFRESH_METRICS = """
MATCH (u:User)
OPTIONAL MATCH (u)-[:FRIEND]-(n)
WITH u, collect(DISTINCT n) AS ns
WITH u, ns, size(ns) AS deg
// u itself is excluded from the neighbourhood on purpose. Including it counts
// u's own spokes as internal edges, which makes a star — the most OPEN shape
// there is — score as closed as a clique. What matters is whether u's friends
// know each other and whether they know anyone outside.
CALL (u, ns) {
  UNWIND ns AS a
  OPTIONAL MATCH (a)-[:FRIEND]-(x)
  WHERE x <> u
  RETURN sum(CASE WHEN x IN ns THEN 1 ELSE 0 END) AS inside_ends,
         sum(CASE WHEN x IS NOT NULL AND NOT x IN ns THEN 1 ELSE 0 END) AS boundary
}
WITH u, deg, (toFloat(inside_ends) / 2.0) AS internal, toFloat(boundary) AS boundary
SET u.degree = deg,
    u.closure = CASE WHEN deg < 2 OR (internal + boundary) = 0 THEN 0.0
                     ELSE internal / (internal + boundary) END
"""


async def refresh_graph_metrics() -> None:
    """Recompute degree and clustering for every node."""
    try:
        await run_write(REFRESH_METRICS)
        logger.info("graph: refreshed degree/clustering")
    except Exception:
        logger.warning("graph: metric refresh failed", exc_info=True)
