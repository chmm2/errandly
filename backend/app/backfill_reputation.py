"""Recompute the provenance-weighted reputation ranking actually reads.

    docker compose exec backend python -m app.backfill_reputation

Matching ranks on `users.effective_reputation`, not on the plain average a
runner sees. That column is a cache: it is refreshed when a rating lands, which
is correct going forward and does nothing at all for ratings that arrived
before the weighting existed.

The result is silent and one-directional. A runner rated 5.0 by eight people
sits at the 3.50 default with confidence 0, is ranked exactly like somebody
nobody has ever rated, and is simply offered less work than they earned. There
is no error anywhere - the column has a perfectly valid value, just not one
derived from their ratings.

Idempotent: recompute is a pure function of the rating history, so running this
twice changes nothing and running it after a partial failure finishes the job.
"""

import asyncio
import logging

from sqlalchemy import or_, select

import app.models  # noqa: F401 — register every mapper
from app.core.database import SessionLocal
from app.modules.auth.models import User
from app.modules.errands.models import Rating
from app.modules.fraud import reputation

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("backfill")


async def backfill() -> int:
    async with SessionLocal() as db:
        # Anyone with a rating history, however it got there. Not just
        # rating_count > 0: that counter is maintained by the same path that
        # maintains the cache, so trusting it would skip exactly the rows most
        # likely to be wrong.
        rated = select(Rating.ratee_id).distinct()
        users = list(
            await db.scalars(
                select(User).where(or_(User.rating_count > 0, User.id.in_(rated)))
            )
        )
        logger.info("users with a rating history: %d", len(users))

        changed = 0
        for user in users:
            before = float(user.effective_reputation)
            await reputation.recompute(db, user.id)
            after = float(user.effective_reputation)
            if abs(after - before) > 0.001:
                changed += 1
                logger.info(
                    "  %-22s %.2f -> %.2f  (confidence %.3f)",
                    user.display_name,
                    before,
                    after,
                    float(user.rating_confidence),
                )

        await db.commit()
        logger.info("reputations corrected: %d of %d", changed, len(users))
        return changed


if __name__ == "__main__":
    asyncio.run(backfill())
