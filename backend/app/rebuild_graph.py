"""Rebuild the Neo4j read model from Postgres.

    docker compose exec backend python -m app.rebuild_graph

The graph is derived: friendships and settlements live in Postgres, and the
social-graph consumer projects them as they happen. That design is only
actually safe if the projection can be *replayed*, and until now it could not
be — the consumer processes new events only, so a lost volume, a reset
container, or a consumer that was down during a burst left the graph
permanently short with nothing to say so.

That failure is silent by construction. Every graph read degrades to a neutral
value on purpose, so an empty graph looks exactly like a campus where nobody
has friends: matching quietly falls back to distance-only and no error appears
anywhere. This module is what makes the "rebuildable" claim true rather than
aspirational.

Idempotent: every write is a MERGE, so running it twice changes nothing and
running it against a populated graph repairs gaps rather than duplicating.
"""

import asyncio
import logging

from sqlalchemy import or_, select

import app.models  # noqa: F401 — register every mapper
from app.core.database import SessionLocal
from app.core.graph import close_driver, ensure_schema, run_write
from app.modules.auth.models import User
from app.modules.errands.models import Errand
from app.modules.social.models import Friendship
from app.modules.social.projection import (
    LINK_FRIENDS,
    RECORD_PAYMENT,
    UPSERT_USER,
)
from app.modules.social.projection import refresh_graph_metrics

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("rebuild")


async def rebuild() -> None:
    await ensure_schema()

    async with SessionLocal() as db:
        friendships = list(
            await db.scalars(
                select(Friendship).where(Friendship.status == "ACCEPTED")
            )
        )
        # Only settled errands: a PAID edge must mean money actually moved, so
        # this mirrors exactly what the ORDER_COMPLETED projection writes.
        errands = list(
            await db.scalars(
                select(Errand).where(
                    Errand.status == "COMPLETED",
                    Errand.runner_id.is_not(None),
                    Errand.deleted_at.is_(None),
                )
            )
        )

        involved: set[str] = set()
        for f in friendships:
            involved.update({str(f.user_lo), str(f.user_hi)})
        for e in errands:
            involved.update({str(e.requester_id), str(e.runner_id)})

        names: dict[str, str | None] = {}
        if involved:
            for u in await db.scalars(
                select(User).where(
                    or_(*[User.id == i for i in involved])
                    if len(involved) < 500
                    else User.id.in_(list(involved))
                )
            ):
                names[str(u.id)] = u.display_name

    for uid in involved:
        await run_write(UPSERT_USER, id=uid, name=names.get(uid))
    logger.info("users projected: %d", len(involved))

    for f in friendships:
        await run_write(
            LINK_FRIENDS,
            a=str(f.user_lo),
            b=str(f.user_hi),
            at=f.responded_at.isoformat() if f.responded_at else None,
        )
    logger.info("friendships projected: %d", len(friendships))

    for e in errands:
        await run_write(
            RECORD_PAYMENT,
            from_id=str(e.requester_id),
            to_id=str(e.runner_id),
            errand_id=str(e.id),
            # Same figure the live projection uses: the runner's fee plus cash
            # handed over. items_total is excluded, never settling through the
            # platform.
            amount=float(e.reward or 0) + float(e.collect_amount or 0),
            at=e.completed_at.isoformat() if e.completed_at else None,
        )
    logger.info("settlements projected: %d", len(errands))

    await refresh_graph_metrics()
    logger.info("degree, closure and circulation recomputed")


async def main() -> None:
    try:
        await rebuild()
    finally:
        await close_driver()


if __name__ == "__main__":
    asyncio.run(main())
