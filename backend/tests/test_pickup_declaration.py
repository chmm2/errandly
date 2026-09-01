"""The runner declares what they actually paid, and that is what gets paid back.

Escrow holds the estimate plus headroom so a runner who paid over the estimate
is still made whole. That only works if somebody states the real figure -
without it the platform can reimburse nothing but its own guess, and the
headroom is decoration.
"""

import uuid
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.core.database import SessionLocal
from app.modules.errands import service as errands
from app.modules.errands.models import Errand
from app.modules.ledger import service as ledger

pytestmark = pytest.mark.asyncio(loop_scope="session")

NEAR = {"lat": 12.9692, "lng": 79.1559}


async def _fund(user_id: uuid.UUID, amount: str) -> None:
    async with SessionLocal() as db:
        current = await ledger.balance(db, user_id)
        target = Decimal(amount)
        if target > current:
            await ledger.topup(db, user_id, target - current, memo="Test funding")
        await db.commit()


async def _place(client, headers, *, collect: int, reward: int = 30) -> dict:
    return (
        await client.post(
            "/errands",
            json={
                "category": "CUSTOM",
                "title": "Groceries",
                "pickup_label": "Campus Store",
                "drop_lat": NEAR["lat"],
                "drop_lng": NEAR["lng"],
                "reward": reward,
                "collect_amount": collect,
            },
            headers=headers,
        )
    ).json()


async def test_pickup_asks_for_nothing(client, campus, make_user):
    """Marking an errand picked up carries no amount.

    A lump sum cannot be checked against anything. Prices are reported per
    item instead, where each one can be judged against the reference for that
    item at that store - and fixed-price goods need no report at all, so
    demanding one here would be asking the runner to retype the menu.
    """
    requester_id, r_headers = await make_user("Requester")
    _, run_headers = await make_user("Runner")
    await _fund(requester_id, "1000")

    errand = await _place(client, r_headers, collect=300)
    await client.post(f"/errands/{errand['id']}/accept", headers=run_headers)

    bare = await client.post(f"/errands/{errand['id']}/pickup", headers=run_headers)
    assert bare.status_code == 200, bare.text
    assert bare.json()["status"] == "IN_PROGRESS"
    assert bare.json()["amount_spent"] is None, "nothing was declared, so nothing is recorded"


async def test_a_nonsense_amount_is_still_refused(client, campus, make_user):
    """Optional is not unchecked. A body that names an amount must still make
    sense, or a negative number would credit the runner by subtraction."""
    requester_id, r_headers = await make_user("Requester")
    _, run_headers = await make_user("Runner")
    await _fund(requester_id, "1000")

    errand = await _place(client, r_headers, collect=300)
    await client.post(f"/errands/{errand['id']}/accept", headers=run_headers)

    negative = await client.post(
        f"/errands/{errand['id']}/pickup",
        json={"amount_spent": -50},
        headers=run_headers,
    )
    assert negative.status_code == 422


async def test_the_declaration_is_recorded_and_returned(client, campus, make_user):
    requester_id, r_headers = await make_user("Requester")
    _, run_headers = await make_user("Runner")
    await _fund(requester_id, "1000")

    errand = await _place(client, r_headers, collect=300)
    await client.post(f"/errands/{errand['id']}/accept", headers=run_headers)

    resp = await client.post(
        f"/errands/{errand['id']}/pickup",
        json={"amount_spent": 310},
        headers=run_headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "IN_PROGRESS"
    assert resp.json()["amount_spent"] == 310.0

    async with SessionLocal() as db:
        row = await db.scalar(
            select(Errand).where(Errand.id == uuid.UUID(errand["id"]))
        )
        assert Decimal(str(row.amount_spent)) == Decimal("310.00")


async def test_only_the_assigned_runner_can_declare(client, campus, make_user):
    requester_id, r_headers = await make_user("Requester")
    _, run_headers = await make_user("Runner")
    _, stranger = await make_user("Stranger")
    await _fund(requester_id, "1000")

    errand = await _place(client, r_headers, collect=300)
    await client.post(f"/errands/{errand['id']}/accept", headers=run_headers)

    resp = await client.post(
        f"/errands/{errand['id']}/pickup",
        json={"amount_spent": 9999},
        headers=stranger,
    )
    assert resp.status_code == 403


async def test_settlement_pays_the_declared_amount_not_the_estimate(
    client, campus, make_user
):
    """The headroom exists for exactly this: ₹300 estimated, ₹340 really paid.

    The declared figure is what settlement pays, whichever side of the
    estimate it falls on. Here the runner found it cheaper than quoted, and the
    difference has to go back to the requester rather than being kept.
    """
    requester_id, r_headers = await make_user("Requester")
    runner_id, run_headers = await make_user("Runner")
    await _fund(requester_id, "1000")

    async with SessionLocal() as db:
        before = await ledger.balance(db, runner_id)

    errand = await _place(client, r_headers, collect=300)
    await client.post(f"/errands/{errand['id']}/accept", headers=run_headers)
    await client.post(
        f"/errands/{errand['id']}/pickup",
        json={"amount_spent": 280},
        headers=run_headers,
    )

    async with SessionLocal() as db:
        declared = await errands.declared_spend(db, uuid.UUID(errand["id"]))
        assert declared == Decimal("280.00")

        await ledger.release_hold(
            db,
            errand_id=uuid.UUID(errand["id"]),
            runner_id=runner_id,
            reward=Decimal("30"),
            reimbursement=declared,
        )
        await db.commit()

        earned = await ledger.balance(db, runner_id) - before
        assert earned == Decimal("310.00"), (
            "₹280 actually paid + ₹30 fee, not the ₹300 estimate"
        )


async def test_never_declared_is_not_the_same_as_declared_zero(client, campus, make_user):
    """An errand from before this step existed must not reimburse ₹0.

    Collapsing "never said" into "said nothing" would quietly pay the runner
    their fee alone and hand the whole basket back to the requester.
    """
    requester_id, r_headers = await make_user("Requester")
    _, run_headers = await make_user("Runner")
    await _fund(requester_id, "1000")

    errand = await _place(client, r_headers, collect=300)
    await client.post(f"/errands/{errand['id']}/accept", headers=run_headers)

    async with SessionLocal() as db:
        assert await errands.declared_spend(db, uuid.UUID(errand["id"])) is None

    await client.post(
        f"/errands/{errand['id']}/pickup",
        json={"amount_spent": 0},
        headers=run_headers,
    )

    async with SessionLocal() as db:
        assert await errands.declared_spend(db, uuid.UUID(errand["id"])) == Decimal("0.00")
