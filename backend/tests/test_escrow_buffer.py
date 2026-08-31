"""Escrow headroom: hold more than the estimate, give back what is not used.

A runner discovers the real price at the counter, with their own cash already
spent. If the requester's wallet was sized to the estimate exactly, a ₹25
difference leaves the runner out of pocket for the platform's optimism. So the
hold carries a percentage of the ESTIMATED SPEND on top — never of the fee,
which is fixed and known — and whatever is not needed goes back at settlement.
"""

import uuid
from decimal import Decimal

import pytest
from sqlalchemy import update

from app.core.database import SessionLocal
from app.modules.auth.models import User
from app.modules.ledger import service as ledger
from app.modules.ledger.models import EscrowHold

pytestmark = pytest.mark.asyncio(loop_scope="session")

NEAR = {"lat": 12.9692, "lng": 79.1559}


async def _fund(user_id: uuid.UUID, amount: str) -> None:
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


async def _hold(errand_id: uuid.UUID) -> EscrowHold:
    async with SessionLocal() as db:
        return await db.get(EscrowHold, uuid.UUID(str(errand_id)))


async def _promote(user_id: uuid.UUID, role: str) -> None:
    async with SessionLocal() as db:
        await db.execute(update(User).where(User.id == user_id).values(role=role))
        await db.commit()


# ------------------------------------------------------------------ the maths


async def test_the_worked_example(client, campus, make_user):
    """The scenario as specified.

    ₹500 wallet. ₹300 estimated spend, 15% headroom, ₹30 fee.
    Hold ₹375, leaving ₹125 available. Runner actually spends ₹310, so they
    receive ₹340 and the unused ₹35 comes back — ending at ₹160.
    """
    requester_id, r_headers = await make_user("Requester")
    runner_id, run_headers = await make_user("Runner")
    await _fund(requester_id, "500")
    await _fund(runner_id, "0")

    errand = (
        await client.post(
            "/errands",
            json={
                "category": "CUSTOM",
                "title": "Groceries",
                "pickup_label": "Campus Store",
                "drop_lat": NEAR["lat"],
                "drop_lng": NEAR["lng"],
                "reward": 30,
                "collect_amount": 300,
            },
            headers=r_headers,
        )
    ).json()

    hold = await _hold(errand["id"])
    assert Decimal(str(hold.buffer)) == Decimal("45.00"), "15% of the ₹300 spend"
    assert Decimal(str(hold.amount)) == Decimal("375.00"), "300 + 45 + 30"
    assert await _balance(requester_id) == Decimal("125.00")

    resp = await client.post(f"/errands/{errand['id']}/accept", headers=run_headers)
    assert resp.status_code == 200, resp.text

    # The runner reports what they actually paid: ₹310, above the estimate but
    # inside the headroom.
    async with SessionLocal() as db:
        await ledger.release_hold(
            db,
            errand_id=uuid.UUID(errand["id"]),
            runner_id=runner_id,
            reward=Decimal("30"),
            reimbursement=Decimal("310"),
        )
        await db.commit()

    assert await _balance(runner_id) == Decimal("340.00"), "₹310 spent + ₹30 fee"
    assert await _balance(requester_id) == Decimal("160.00"), "₹125 + the unused ₹35"


async def test_the_fee_is_not_padded(client, campus, make_user):
    """Headroom protects an uncertain spend. The fee is fixed and known, so
    padding it would lock money that could never be needed."""
    requester_id, r_headers = await make_user("Requester")
    await _fund(requester_id, "1000")

    errand = (
        await client.post(
            "/errands",
            json={
                "category": "CUSTOM",
                "title": "Big fee small basket",
                "pickup_label": "Gate",
                "drop_lat": NEAR["lat"],
                "drop_lng": NEAR["lng"],
                "reward": 200,
                "collect_amount": 100,
            },
            headers=r_headers,
        )
    ).json()

    hold = await _hold(errand["id"])
    assert Decimal(str(hold.buffer)) == Decimal("15.00"), "15% of 100, not of 300"
    assert Decimal(str(hold.amount)) == Decimal("315.00")


async def test_an_errand_with_no_spend_holds_no_buffer(client, campus, make_user):
    """A delivery of something already paid for has nothing to be uncertain
    about, so the requester's money should not be tied up for it."""
    requester_id, r_headers = await make_user("Requester")
    await _fund(requester_id, "500")

    errand = (
        await client.post(
            "/errands",
            json={
                "category": "PARCEL",
                "title": "Collect a parcel",
                "pickup_label": "Main Gate",
                "drop_lat": NEAR["lat"],
                "drop_lng": NEAR["lng"],
                "reward": 40,
                "collect_amount": 0,
            },
            headers=r_headers,
        )
    ).json()

    hold = await _hold(errand["id"])
    assert Decimal(str(hold.buffer)) == Decimal("0.00")
    assert Decimal(str(hold.amount)) == Decimal("40.00")


async def test_the_wallet_shows_both_partitions(client, campus, make_user):
    """Available and held, separately. Escrowed money has already left the
    balance, and naming it is what explains where it went."""
    requester_id, r_headers = await make_user("Requester")
    await _fund(requester_id, "500")

    before = (await client.get("/ledger/me/wallet", headers=r_headers)).json()
    assert before["balance"] == 500.0
    assert before["held"] == 0.0

    await client.post(
        "/errands",
        json={
            "category": "CUSTOM",
            "title": "Groceries",
            "pickup_label": "Store",
            "drop_lat": NEAR["lat"],
            "drop_lng": NEAR["lng"],
            "reward": 30,
            "collect_amount": 300,
        },
        headers=r_headers,
    )

    after = (await client.get("/ledger/me/wallet", headers=r_headers)).json()
    assert after["balance"] == 125.0, "available to spend"
    assert after["held"] == 375.0, "ring-fenced against the live order"
    assert after["balance"] + after["held"] == 500.0, "nothing vanished"


# --------------------------------------------------------------- overspend


async def test_spending_past_the_headroom_does_not_break_settlement(
    client, campus, make_user
):
    """The runner's fee is ring-fenced and settlement still completes.

    Raising here would fail a Kafka event that is then redelivered, so an
    unpayable errand would retry forever. Paying what is held and recording the
    gap is recoverable; a stuck consumer is not.
    """
    requester_id, r_headers = await make_user("Requester")
    runner_id, run_headers = await make_user("Runner")
    await _fund(requester_id, "500")
    await _fund(runner_id, "0")

    errand = (
        await client.post(
            "/errands",
            json={
                "category": "CUSTOM",
                "title": "Groceries",
                "pickup_label": "Store",
                "drop_lat": NEAR["lat"],
                "drop_lng": NEAR["lng"],
                "reward": 30,
                "collect_amount": 300,
            },
            headers=r_headers,
        )
    ).json()
    await client.post(f"/errands/{errand['id']}/accept", headers=run_headers)

    # ₹400 spent against a ₹345 ceiling — ₹55 past the headroom.
    async with SessionLocal() as db:
        await ledger.release_hold(
            db,
            errand_id=uuid.UUID(errand["id"]),
            runner_id=runner_id,
            reward=Decimal("30"),
            reimbursement=Decimal("400"),
        )
        await db.commit()

    # The fee survives intact; reimbursement is capped at what was held.
    assert await _balance(runner_id) == Decimal("375.00"), "₹345 held for spend + ₹30 fee"

    hold = await _hold(errand["id"])
    assert Decimal(str(hold.released_amount)) <= Decimal(str(hold.amount)), (
        "a payout can never exceed its hold"
    )
    assert await _balance(requester_id) == Decimal("125.00"), "nothing left to refund"
