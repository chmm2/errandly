"""A payout bigger than the hold is frozen, not quietly capped.

The requester locked an exact amount and agreed to nothing beyond it. When the
runner's declared spend plus their fee exceeds that, neither automatic answer
is defensible: paying in full charges the requester money they never committed,
and paying the capped amount makes the runner absorb a gap that is either a
shop's price rise or an inflated claim. Nothing moves until a person decides.
"""

import uuid
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.core.database import SessionLocal
from app.modules.fraud.models import FraudFlag
from app.modules.ledger import service as ledger
from app.modules.ledger.models import EscrowHold
from app.workers.consumers import handle_settlement

pytestmark = pytest.mark.asyncio(loop_scope="session")

NEAR = {"lat": 12.9692, "lng": 79.1559}


async def _fund(user_id: uuid.UUID, amount: str) -> None:
    """Pin a wallet to an exact figure. The fixture starts users rich, so the
    arithmetic in these tests only reads if we bring them back down first."""
    async with SessionLocal() as db:
        current = await ledger.balance(db, user_id)
        target = Decimal(amount)
        if target > current:
            await ledger.topup(db, user_id, target - current, memo="Test funding")
        elif target < current:
            await ledger.clawback(
                db, user_id=user_id, amount=current - target, memo="Test funding"
            )
        await db.commit()


async def _balance(user_id: uuid.UUID) -> Decimal:
    async with SessionLocal() as db:
        return await ledger.balance(db, user_id)


async def _run(client, r_headers, run_headers, *, collect: int, reward: int, spent):
    """Place → accept → declare `spent` → deliver → complete → settle."""
    errand = (
        await client.post(
            "/errands",
            json={
                "category": "CUSTOM",
                "title": "Canteen run",
                "pickup_label": "Campus Store",
                "drop_lat": NEAR["lat"],
                "drop_lng": NEAR["lng"],
                "reward": reward,
                "collect_amount": collect,
            },
            headers=r_headers,
        )
    ).json()
    eid = errand["id"]
    await client.post(f"/errands/{eid}/accept", headers=run_headers)
    await client.post(
        f"/errands/{eid}/pickup", json={"amount_spent": spent}, headers=run_headers
    )
    await client.post(f"/errands/{eid}/deliver", headers=run_headers)
    await client.post(f"/errands/{eid}/complete", headers=r_headers)
    return uuid.UUID(eid)


async def _settle(errand_id, runner_id, reward, collect, title="Canteen run"):
    event = {
        "event_id": str(uuid.uuid4()),
        "event_type": "ORDER_COMPLETED",
        "payload": {
            "errand_id": str(errand_id),
            "runner_id": str(runner_id),
            "reward": reward,
            "collect_amount": collect,
            "title": title,
        },
    }
    async with SessionLocal() as db:
        await handle_settlement(db, event)
        await db.commit()


async def test_a_payout_past_the_hold_moves_no_money(client, campus, make_user):
    """₹300 estimate holds ₹375. Declaring ₹400 needs ₹430 — nothing moves."""
    requester_id, r_headers = await make_user("Requester")
    runner_id, run_headers = await make_user("Runner")
    await _fund(requester_id, "1000")

    runner_before = await _balance(runner_id)
    eid = await _run(client, r_headers, run_headers, collect=300, reward=30, spent=400)

    assert await _balance(requester_id) == Decimal("625.00"), "still holding 375"
    await _settle(eid, runner_id, 30, 300)

    assert await _balance(runner_id) == runner_before, "the runner is paid nothing yet"
    assert await _balance(requester_id) == Decimal("625.00"), (
        "the requester is charged nothing beyond what they locked"
    )

    async with SessionLocal() as db:
        hold = await db.get(EscrowHold, eid)
        assert hold.status == "PENDING_REVIEW"
        assert Decimal(str(hold.released_amount)) == Decimal("0.00")
        assert hold.settled_at is None, "frozen, not finished"


async def test_the_money_stays_in_the_requesters_held_partition(
    client, campus, make_user
):
    """Blocked is not refunded. The wallet must still show it as committed."""
    requester_id, r_headers = await make_user("Requester")
    runner_id, run_headers = await make_user("Runner")
    await _fund(requester_id, "1000")

    eid = await _run(client, r_headers, run_headers, collect=300, reward=30, spent=400)
    await _settle(eid, runner_id, 30, 300)

    wallet = (await client.get("/ledger/me/wallet", headers=r_headers)).json()
    assert wallet["balance"] == 625.0
    assert wallet["held"] == 375.0, "still ring-fenced against the disputed order"
    assert wallet["balance"] + wallet["held"] == 1000.0, "nothing vanished"


async def test_the_block_raises_a_flag_for_an_admin(client, campus, make_user):
    requester_id, r_headers = await make_user("Requester")
    runner_id, run_headers = await make_user("Runner")
    await _fund(requester_id, "1000")

    eid = await _run(client, r_headers, run_headers, collect=300, reward=30, spent=400)
    await _settle(eid, runner_id, 30, 300)

    async with SessionLocal() as db:
        flag = await db.scalar(
            select(FraudFlag).where(
                FraudFlag.errand_id == eid, FraudFlag.rule == "PAYOUT_EXCEEDS_HOLD"
            )
        )
        assert flag is not None, "an admin has to be told there is something to decide"
        assert flag.status == "OPEN"
        assert flag.user_id == runner_id
        # 400 + 30 = 430 owed against 375 held.
        assert flag.details["held"] == 375.0
        assert flag.details["payable"] == 430.0
        assert flag.details["gap"] == 55.0


async def test_an_admin_siding_with_the_runner_pays_at_most_the_hold(
    client, campus, make_user
):
    """The ceiling survives review. The requester committed ₹375 and cannot be
    made to pay the ₹430 the runner asked for, whoever is believed."""
    requester_id, r_headers = await make_user("Requester")
    runner_id, run_headers = await make_user("Runner")
    await _fund(requester_id, "1000")

    runner_before = await _balance(runner_id)
    eid = await _run(client, r_headers, run_headers, collect=300, reward=30, spent=400)
    await _settle(eid, runner_id, 30, 300)

    async with SessionLocal() as db:
        await ledger.resolve_withheld(
            db, errand_id=eid, runner_id=runner_id, pay_runner=True
        )
        await db.commit()

    assert await _balance(runner_id) - runner_before == Decimal("375.00"), (
        "the whole hold, and not a rupee more"
    )
    assert await _balance(requester_id) == Decimal("625.00")

    async with SessionLocal() as db:
        hold = await db.get(EscrowHold, eid)
        assert hold.status == "RELEASED"


async def test_a_payout_inside_the_hold_still_settles_normally(
    client, campus, make_user
):
    """The guard must not catch honest overspend the headroom was built for."""
    requester_id, r_headers = await make_user("Requester")
    runner_id, run_headers = await make_user("Runner")
    await _fund(requester_id, "1000")

    runner_before = await _balance(runner_id)
    eid = await _run(client, r_headers, run_headers, collect=300, reward=30, spent=340)
    await _settle(eid, runner_id, 30, 300)

    assert await _balance(runner_id) - runner_before == Decimal("370.00")
    assert await _balance(requester_id) == Decimal("630.00"), "unused ₹5 returned"

    async with SessionLocal() as db:
        hold = await db.get(EscrowHold, eid)
        assert hold.status == "RELEASED"
