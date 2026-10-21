"""Neo4j access for the social graph.

The graph is a **derived read model**. Postgres `friendships` is the source of
truth; this store is projected from the event log by the social-graph consumer
and can be deleted and rebuilt at any time. Two consequences shape everything
here:

  * No write path outside the projection consumer. Nothing in a request handler
    writes to Neo4j, so a graph write can never be the reason a user-facing
    action fails.
  * Every read is behind a circuit breaker and returns a neutral value on
    failure. Losing the graph must degrade matching to distance-only ranking,
    which is exactly what the platform did before it existed — never an outage.
"""

import logging

from neo4j import AsyncDriver, AsyncGraphDatabase

from app.core.config import settings
from app.core.resilience import CircuitBreaker, CircuitOpenError

logger = logging.getLogger(__name__)

_driver: AsyncDriver | None = None

# Reads and writes get separate breakers. A projection consumer hammering a
# dead Neo4j should not trip the breaker that request-path reads rely on, and
# vice versa — they fail for different reasons and recover on different clocks.
read_breaker = CircuitBreaker("neo4j-read", failure_threshold=5, reset_timeout=30.0)
write_breaker = CircuitBreaker("neo4j-write", failure_threshold=5, reset_timeout=30.0)


def driver() -> AsyncDriver:
    global _driver
    if _driver is None:
        _driver = AsyncGraphDatabase.driver(
            settings.neo4j_url,
            auth=(settings.neo4j_user, settings.neo4j_password),
            max_connection_pool_size=20,
        )
    return _driver


async def close_driver() -> None:
    global _driver
    if _driver is not None:
        await _driver.close()
        _driver = None


async def run_read(cypher: str, **params) -> list[dict]:
    """Run a read query. Returns [] if the graph is unavailable.

    Callers must treat [] as 'no social information', not 'no relationship' —
    the difference matters when ranking, and is why the ranker falls back to
    distance rather than assuming everyone is a stranger.
    """

    async def _go() -> list[dict]:
        async with driver().session() as session:
            result = await session.run(cypher, **params)
            return [record.data() async for record in result]

    try:
        return await read_breaker.call(_go)
    except CircuitOpenError:
        return []
    except Exception:
        logger.warning("neo4j read failed; degrading to no-social-info", exc_info=True)
        return []


async def run_write(cypher: str, **params) -> None:
    """Run a write query. Raises on failure so the Kafka consumer does not mark
    the event processed — the projection retries on redelivery rather than
    silently losing a node."""

    async def _go() -> None:
        async with driver().session() as session:
            await session.run(cypher, **params)

    await write_breaker.call(_go)


SCHEMA_STATEMENTS = [
    "CREATE CONSTRAINT user_id IF NOT EXISTS FOR (u:User) REQUIRE u.id IS UNIQUE",
    "CREATE INDEX friend_since IF NOT EXISTS FOR ()-[r:FRIEND]-() ON (r.since)",
    "CREATE INDEX paid_at IF NOT EXISTS FOR ()-[r:PAID]-() ON (r.at)",
]


async def ensure_schema() -> None:
    """Idempotent constraint/index creation, run at consumer startup."""
    for stmt in SCHEMA_STATEMENTS:
        try:
            await run_write(stmt)
        except Exception:
            logger.warning("neo4j schema statement failed: %s", stmt, exc_info=True)
