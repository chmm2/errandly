"""Wallet partitions, and what settlement does when the hold runs out.

Headroom itself now lives in test_non_mrp_buffer.py, because which part of an
order is padded is a question about MRP, not about escrow. What is tested here
is what escrow owes regardless of the base: the two partitions always sum to
the wallet, and a payout larger than the hold degrades safely rather than
failing the Kafka event that carries it.
"""

import uuid
from decimal import Decimal

import pytest
from sqlalchemy import update

from app.core.config import settings
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


async def test_the_wallet_shows_both_partitions(client, campus, make_user):
    """Available and held, separately. Escrowed money has already left the
    balance, and naming it is what explains where it went."""
    requester_id, r_headers = await make_user("Requester")
    await _fund(requester_id, "500")

    before = (await client.get("/ledger/me/wallet", headers=r_headers)).json()
    assert before["balance"] == 500.0
    assert before["held"] == 0.0
    # The order screens quote the locked total before anything is placed, so
    # the rate has to travel with the wallet. Hardcoding it in the client is
    # how a checkout button starts promising a number the wallet disagrees with.
    assert before["buffer_pct"] == settings.escrow_buffer_pct

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
    assert after["balance"] == 170.0, "available to spend"
    assert after["held"] == 330.0, "300 stated cash + 30 fee, no padding"
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

    # ₹400 spent against a ₹300 ceiling — ₹100 past what was held.
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
    assert await _balance(runner_id) == Decimal("330.00"), "₹300 held for spend + ₹30 fee"

    hold = await _hold(errand["id"])
    assert Decimal(str(hold.released_amount)) <= Decimal(str(hold.amount)), (
        "a payout can never exceed its hold"
    )
    assert await _balance(requester_id) == Decimal("170.00"), "nothing left to refund"
