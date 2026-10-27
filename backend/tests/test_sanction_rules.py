"""Who may sanction whom, and how a sanction is undone.

Three rules from the paper review:

1. Only price-claim flags feed the automatic strike ladder. Ring and
   rating-farming flags are relational inferences a person has to weigh.
2. The ladder may warn, demote and pause on open flags, but the last step,
   suspending the account, waits for flags a human has upheld.
3. Dismissing a flag lifts a running pause the remaining flags no longer
   justify, and marks the strike lifted rather than deleting it.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.core.database import SessionLocal
from app.core.redis import redis_client
from app.modules.auth.models import User
from app.modules.fraud import service as fraud
from app.modules.fraud.models import FraudFlag, UserStrike
from app.modules.runners.models import RunnerProfile

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def _flags(user_id: uuid.UUID, n: int, rule="CLAIM_ABOVE_REFERENCE", status="OPEN"):
    async with SessionLocal() as db:
        ids = []
        for _ in range(n):
            flag = FraudFlag(user_id=user_id, rule=rule, severity=2, status=status, details={})
            db.add(flag)
            await db.flush()
            ids.append(flag.id)
        await db.commit()
    return ids


async def _ladder(user_id: uuid.UUID) -> list[str]:
    """Run the ladder until it stops escalating; return the actions on file."""
    async with SessionLocal() as db:
        runner = await db.get(User, user_id)
        while await fraud.evaluate_pattern(db, redis_client, runner):
            pass
        await db.commit()
        return [s.action for s in await db.scalars(
            select(UserStrike).where(UserStrike.user_id == user_id).order_by(UserStrike.level)
        )]


async def test_ring_flags_do_not_feed_the_strike_ladder(client, campus, make_user):
    user_id, _ = await make_user("Ring Member")
    await _flags(user_id, 12, rule="COLLUSION_RING")
    assert await _ladder(user_id) == []


async def test_open_flags_alone_stop_short_of_account_suspension(client, campus, make_user):
    user_id, _ = await make_user("Runner")
    async with SessionLocal() as db:
        db.add(RunnerProfile(user_id=user_id, campus_id=campus))
        await db.commit()
    await _flags(user_id, 12)
    actions = await _ladder(user_id)
    assert actions == ["WARNING", "REPUTATION_PENALTY", "RUNNER_SUSPENDED"]
    async with SessionLocal() as db:
        assert (await db.get(User, user_id)).account_status != "SUSPENDED"


async def test_upheld_flags_reach_account_suspension(client, campus, make_user):
    user_id, _ = await make_user("Runner")
    async with SessionLocal() as db:
        db.add(RunnerProfile(user_id=user_id, campus_id=campus))
        await db.commit()
    await _flags(user_id, 12, status="UPHELD")
    assert (await _ladder(user_id))[-1] == "ACCOUNT_SUSPENDED"


async def test_dismissing_a_flag_lifts_a_pause_it_no_longer_justifies(
    client, campus, make_user
):
    user_id, _ = await make_user("Runner")
    admin_id, _ = await make_user("Admin")
    async with SessionLocal() as db:
        db.add(RunnerProfile(user_id=user_id, campus_id=campus))
        await db.commit()
    ids = await _flags(user_id, 8)
    assert (await _ladder(user_id))[-1] == "RUNNER_SUSPENDED"
    async with SessionLocal() as db:
        profile = await db.get(RunnerProfile, user_id)
        assert profile.fraud_blocked_until > datetime.now(UTC) + timedelta(days=1)

    async with SessionLocal() as db:
        admin = await db.get(User, admin_id)
        flag = await db.get(FraudFlag, ids[0])
        await fraud.review_flag(db, redis_client, flag=flag, admin=admin, uphold=False)
        await db.commit()

    async with SessionLocal() as db:
        assert (await db.get(RunnerProfile, user_id)).fraud_blocked_until is None
        pause = await db.scalar(select(UserStrike).where(
            UserStrike.user_id == user_id, UserStrike.action == "RUNNER_SUSPENDED"))
        assert pause.lifted_at is not None, "kept as history, marked lifted"
