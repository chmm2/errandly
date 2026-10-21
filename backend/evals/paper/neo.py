"""Loading simulated campuses into a throwaway Neo4j.

The experiments wipe the graph between trials, so this module refuses to run
against anything that is not the dedicated evaluation container. Pointing it
at the development graph would delete a read model the team uses for demos.

Edges are bulk-loaded with UNWIND rather than replayed event by event through
the projection consumer. The properties written are the ones the projection
writes (FRIEND.since; PAID.errand_id, amount, at), so the production Cypher
that reads them sees the same shape it would see in deployment.
"""

from __future__ import annotations

from app.core import graph
from app.core.config import settings

BATCH = 5000


def assert_throwaway() -> None:
    url = settings.neo4j_url
    if "paper" not in url:
        raise RuntimeError(
            f"Refusing to run graph experiments against {url!r}. They delete every "
            "node between trials. Point NEO4J_URL at the evaluation container "
            "(bolt://errandly-paper-neo4j:7687)."
        )


async def direct(cypher: str, **params) -> list[dict]:
    """A read that raises instead of degrading. Used for checks and timings."""
    async with graph.driver().session() as session:
        result = await session.run(cypher, **params)
        return [r.data() async for r in result]


async def wipe() -> None:
    assert_throwaway()
    while True:
        rows = await direct(
            "MATCH (n) WITH n LIMIT 20000 DETACH DELETE n RETURN count(*) AS c"
        )
        if not rows or rows[0]["c"] == 0:
            break


async def load(users: list[dict], friends: list[dict], payments: list[dict]) -> None:
    """users: {id,name}; friends: {a,b,since}; payments: {src,dst,eid,amount,at}."""
    assert_throwaway()
    await graph.ensure_schema()
    for i in range(0, len(users), BATCH):
        await direct(
            "UNWIND $rows AS u MERGE (n:User {id: u.id}) SET n.name = u.name",
            rows=users[i : i + BATCH],
        )
    for i in range(0, len(friends), BATCH):
        await direct(
            """
            UNWIND $rows AS p
            MATCH (a:User {id: p.a}), (b:User {id: p.b})
            MERGE (a)-[r:FRIEND]-(b)
            ON CREATE SET r.since = p.since
            """,
            rows=friends[i : i + BATCH],
        )
    for i in range(0, len(payments), BATCH):
        await direct(
            """
            UNWIND $rows AS p
            MATCH (a:User {id: p.src}), (b:User {id: p.dst})
            MERGE (a)-[e:PAID {errand_id: p.eid}]->(b)
            ON CREATE SET e.amount = p.amount, e.at = p.at
            """,
            rows=payments[i : i + BATCH],
        )


async def node_metrics() -> dict[str, dict]:
    rows = await direct(
        """
        MATCH (u:User)
        RETURN u.id AS id, coalesce(u.degree, 0) AS degree,
               coalesce(u.closure, 0.0) AS closure,
               coalesce(u.circulation, 0.0) AS circulation,
               coalesce(u.paid_value, 0.0) AS paid_value,
               coalesce(u.paid_txns, 0) AS paid_txns
        """
    )
    return {r["id"]: r for r in rows}
