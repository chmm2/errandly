"""Escrow payments and price-claim fraud detection, end to end.

The money assertions matter more than the endpoint assertions here: a fraud
system that flags correctly but pays out wrongly has failed at the only thing
it was built for.
"""

import uuid
from decimal import Decimal

import pytest
from sqlalchemy import select, update

from app.core.database import SessionLocal
from app.modules.auth.models import User
from app.modules.fraud.models import (
    FraudFlag,
    ItemAlias,
    RunnerPriceClaim,
    UserStrike,
)
from app.modules.fraud.normalize import normalize
from app.modules.ledger import service as ledger
from app.modules.ledger.models import EscrowHold
from app.modules.runners.models import RunnerProfile
from app.workers.consumers import handle_settlement

pytestmark = pytest.mark.asyncio(loop_scope="session")

NEAR = {"lat": 12.9692, "lng": 79.1559}


# ------------------------------------------------------------------ helpers


async def promote(user_id: uuid.UUID, role: str) -> None:
    async with SessionLocal() as db:
        await db.execute(update(User).where(User.id == user_id).values(role=role))
        await db.commit()


async def set_balance(user_id: uuid.UUID, amount: str) -> None:
    """Force a wallet to an exact balance, whatever it holds now."""
    async with SessionLocal() as db:
        current = await ledger.balance(db, user_id)
        target = Decimal(amount)
        if target > current:
            await ledger.topup(db, user_id, target - current, memo="Test adjust")
        elif target < current:
            await ledger.clawback(db, user_id=user_id, amount=current - target, memo="Test adjust")
        await db.commit()


async def balance_of(user_id: uuid.UUID) -> Decimal:
    async with SessionLocal() as db:
        return await ledger.balance(db, user_id)


async def make_admin(client, make_user):
    admin_id, headers = await make_user("Fraud Admin")
    await promote(admin_id, "ADMIN")
    return admin_id, headers


async def price_item(
    client, admin_headers, name="Chicken Puff", price=20, lo=15, hi=30, tolerance=20
):
    """Set a reference price, whether or not one already exists.

    Reference prices are campus-scoped and outlive a single test, and the whole
    suite shares one campus - so this upserts rather than assuming a clean
    slate. Each test then gets the exact band it is reasoning about instead of
    inheriting whatever ran before it.
    """
    body = {
        "display_name": name,
        "reference_price": price,
        "band_min": lo,
        "band_max": hi,
        "tolerance_abs": tolerance,
    }
    resp = await client.post("/fraud/references", json=body, headers=admin_headers)
    if resp.status_code == 201:
        return resp.json()

    assert resp.status_code == 409, resp.text
    existing = (await client.get("/fraud/references", headers=admin_headers)).json()
    match = next(r for r in existing if r["display_name"] == name)
    patched = await client.patch(
        f"/fraud/references/{match['id']}", json=body, headers=admin_headers
    )
    assert patched.status_code == 200, patched.text
    return patched.json()


async def place_order(
    client, headers, reward=30, collect=100, title="Canteen run", pickup=None
):
    # A distinct store per order by default. Claims now teach a per-store
    # reference, so orders sharing a pickup label share a learned price and
    # tests become order-dependent - one test's inflated claims would move the
    # reference a later test is judged against. Pass `pickup` explicitly when a
    # test actually means "the same shop".
    pickup = pickup or f"Shop {uuid.uuid4().hex[:8]}"
    resp = await client.post(
        "/errands",
        json={
            "category": "CUSTOM",
            "title": title,
            "pickup_label": pickup,
            "drop_lat": NEAR["lat"],
            "drop_lng": NEAR["lng"],
            "reward": reward,
            "collect_amount": collect,
        },
        headers=headers,
    )
    return resp


async def accept(client, errand_id, runner_headers):
    resp = await client.post(f"/errands/{errand_id}/accept", headers=runner_headers)
    assert resp.status_code == 200, resp.text
    return resp.json()


async def finish_run(client, errand_id, run_headers, r_headers, spent=0):
    """Drive an accepted errand to COMPLETED.

    Runners have a load cap of 2 concurrent runs, so a test that needs the same
    runner to offend repeatedly has to actually finish each errand rather than
    stacking them.

    These tests settle by hand via settle(), so the amount declared at pickup
    does not drive the payout here - but it is required by the endpoint, so it
    has to be sent.
    """
    for step, headers, body in (
        ("pickup", run_headers, {"amount_spent": spent}),
        ("deliver", run_headers, None),
        ("complete", r_headers, None),
    ):
        resp = await client.post(
            f"/errands/{errand_id}/{step}", json=body, headers=headers
        )
        assert resp.status_code == 200, f"{step}: {resp.text}"


async def settle(errand_id, runner_id, reward, collect, title="Canteen run"):
    """Drive the settlement consumer directly, as the Sprint 4 tests do."""
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


# ------------------------------------------------------------------- escrow


async def test_placing_an_order_moves_money_into_escrow(client, campus, make_user):
    requester_id, headers = await make_user("Requester")
    await set_balance(requester_id, "500")

    resp = await place_order(client, headers, reward=30, collect=100)
    assert resp.status_code == 201, resp.text
    errand_id = resp.json()["id"]

    # 100 estimated spend + 15 headroom (15% of the spend, not the fee) + 30 fee.
    assert await balance_of(requester_id) == Decimal("355.00")

    async with SessionLocal() as db:
        hold = await db.get(EscrowHold, uuid.UUID(errand_id))
    assert hold is not None
    assert hold.status == "HELD"
    assert Decimal(str(hold.buffer)) == Decimal("15.00")
    assert Decimal(str(hold.amount)) == Decimal("145.00")


async def test_an_unfunded_order_is_refused(client, campus, make_user):
    """The hold is the runner's guarantee they will be paid. Without it the
    order must not reach the feed at all."""
    requester_id, headers = await make_user("Broke Requester")
    await set_balance(requester_id, "50")

    resp = await place_order(client, headers, reward=30, collect=100)
    assert resp.status_code == 402, resp.text
    assert "short by" in resp.json()["detail"]

    # Nothing was charged, and no errand exists to be accepted.
    assert await balance_of(requester_id) == Decimal("50.00")


async def test_cancelling_returns_the_full_hold(client, campus, make_user):
    requester_id, headers = await make_user("Requester")
    await set_balance(requester_id, "500")

    errand = (await place_order(client, headers, reward=30, collect=100)).json()
    assert await balance_of(requester_id) == Decimal("355.00")

    resp = await client.post(f"/errands/{errand['id']}/cancel", json={}, headers=headers)
    assert resp.status_code == 200, resp.text

    # Headroom is returned along with everything else - it was only ever a
    # reservation against a spend that never happened.
    assert await balance_of(requester_id) == Decimal("500.00")
    async with SessionLocal() as db:
        hold = await db.get(EscrowHold, uuid.UUID(errand["id"]))
    assert hold.status == "REFUNDED"


async def test_settlement_pays_the_runner_out_of_escrow(client, campus, make_user):
    requester_id, r_headers = await make_user("Requester")
    runner_id, run_headers = await make_user("Runner")
    await set_balance(requester_id, "500")
    await set_balance(runner_id, "0")

    errand = (await place_order(client, r_headers, reward=30, collect=100)).json()
    await accept(client, errand["id"], run_headers)
    await settle(errand["id"], runner_id, reward=30, collect=100)

    assert await balance_of(runner_id) == Decimal("130.00")
    async with SessionLocal() as db:
        hold = await db.get(EscrowHold, uuid.UUID(errand["id"]))
    assert hold.status == "RELEASED"


async def test_a_redelivered_settlement_pays_only_once(client, campus, make_user):
    """Kafka is at-least-once. The ledger's uniqueness gate has to make a
    replay a no-op even if the consumer-level gate is bypassed entirely."""
    requester_id, r_headers = await make_user("Requester")
    runner_id, run_headers = await make_user("Runner")
    await set_balance(requester_id, "500")
    await set_balance(runner_id, "0")

    errand = (await place_order(client, r_headers, reward=30, collect=100)).json()
    await accept(client, errand["id"], run_headers)

    await settle(errand["id"], runner_id, reward=30, collect=100)
    await settle(errand["id"], runner_id, reward=30, collect=100)

    assert await balance_of(runner_id) == Decimal("130.00")


async def test_unspent_hold_is_returned_to_the_requester(client, campus, make_user):
    """The requester quoted 100 for the shopping; the runner reported spending
    60. The other 40 belongs to the requester, not to the platform."""
    requester_id, r_headers = await make_user("Requester")
    runner_id, run_headers = await make_user("Runner")
    admin_id, a_headers = await make_admin(client, make_user)
    await price_item(client, a_headers, price=20, lo=15, hi=30)
    await set_balance(requester_id, "500")
    await set_balance(runner_id, "0")

    errand = (await place_order(client, r_headers, reward=30, collect=100)).json()
    await accept(client, errand["id"], run_headers)

    resp = await client.post(
        f"/fraud/errands/{errand['id']}/claims",
        json={"lines": [{"name": "Chicken Puff", "unit_price": 20, "quantity": 3}]},
        headers=run_headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["total_eligible"] == 60.0

    await settle(errand["id"], runner_id, reward=30, collect=100)

    assert await balance_of(runner_id) == Decimal("90.00")  # 30 reward + 60 spent
    assert await balance_of(requester_id) == Decimal("410.00")  # 500 - 130 + 40 back


# -------------------------------------------------------------------- fraud


async def test_a_claim_at_the_reference_is_clean(client, campus, make_user):
    _, run_headers = await make_user("Runner")
    _, r_headers = await make_user("Requester")
    _, a_headers = await make_admin(client, make_user)
    await price_item(client, a_headers, price=20, lo=15, hi=30, tolerance=20)

    errand = (await place_order(client, r_headers)).json()
    await accept(client, errand["id"], run_headers)
    resp = await client.post(
        f"/fraud/errands/{errand['id']}/claims",
        json={"lines": [{"name": "Chicken Puff", "unit_price": 20, "quantity": 1}]},
        headers=run_headers,
    )
    assert resp.json()["claims"][0]["verdict"] == "OK"


async def test_a_claim_within_tolerance_passes(client, campus, make_user):
    _, run_headers = await make_user("Runner")
    requester_id, r_headers = await make_user("Requester")
    _, a_headers = await make_admin(client, make_user)
    await price_item(client, a_headers, price=20, lo=15, hi=30, tolerance=20)

    errand = (await place_order(client, r_headers)).json()
    await accept(client, errand["id"], run_headers)

    # ₹22 on a ₹20 reference is ₹2 over — inside the ₹20 line, so it is paid in
    # full. It is recorded as ELEVATED rather than OK, because where a runner
    # sits inside the allowance is what the pattern rule later reads.
    resp = await client.post(
        f"/fraud/errands/{errand['id']}/claims",
        json={"lines": [{"name": "chicken puffs", "unit_price": 22, "quantity": 1}]},
        headers=run_headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["claims"][0]["verdict"] == "ELEVATED"
    assert body["claims"][0]["delta_abs"] == 2.0
    assert body["withheld"] == 0.0, "under the line is paid in full"


async def test_an_inflated_claim_is_flagged_and_capped(client, campus, make_user):
    """The core case: quoting 40 for a 20-rupee chicken puff.

    The runner is paid the reference amount, not the claim - so the lie earns
    nothing while the honest part of the errand still pays.
    """
    runner_id, run_headers = await make_user("Runner")
    requester_id, r_headers = await make_user("Requester")
    _, a_headers = await make_admin(client, make_user)
    await price_item(client, a_headers, price=20, lo=15, hi=30, tolerance=20)
    await set_balance(runner_id, "0")

    errand = (await place_order(client, r_headers, reward=30, collect=100)).json()
    await accept(client, errand["id"], run_headers)

    resp = await client.post(
        f"/fraud/errands/{errand['id']}/claims",
        json={"lines": [{"name": "Chicken Puffs", "unit_price": 45, "quantity": 2}]},
        headers=run_headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    claim = body["claims"][0]

    assert claim["verdict"] == "FLAGGED"
    assert claim["item_key"] == "chicken puff"
    assert claim["delta_abs"] == 25.0  # ₹25 over a ₹20 line
    assert body["total_claimed"] == 90.0
    assert body["total_eligible"] == 40.0  # reference 20 x 2
    assert body["withheld"] == 50.0
    assert "on hold" in body["message"]

    async with SessionLocal() as db:
        flags = list(
            await db.scalars(select(FraudFlag).where(FraudFlag.user_id == runner_id))
        )
    assert len(flags) == 1
    assert flags[0].rule == "CLAIM_ABOVE_REFERENCE"

    # Only the eligible amount reaches the runner; the excess stays in escrow.
    await settle(errand["id"], runner_id, reward=30, collect=100)
    assert await balance_of(runner_id) == Decimal("70.00")  # 30 + 40, not 30 + 90

    async with SessionLocal() as db:
        hold = await db.get(EscrowHold, uuid.UUID(errand["id"]))
    assert hold.status == "PENDING_REVIEW"


async def test_an_unpriced_item_is_never_called_fraud(client, campus, make_user):
    """No reference means our gap, not the runner's dishonesty. Pay in full."""
    runner_id, run_headers = await make_user("Runner")
    requester_id, r_headers = await make_user("Requester")

    errand = (await place_order(client, r_headers, reward=30, collect=100)).json()
    await accept(client, errand["id"], run_headers)

    resp = await client.post(
        f"/fraud/errands/{errand['id']}/claims",
        json={"lines": [{"name": "Mystery Pastry", "unit_price": 95, "quantity": 1}]},
        headers=run_headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["claims"][0]["verdict"] == "NO_REFERENCE"
    assert body["withheld"] == 0.0


async def test_misspellings_are_judged_against_the_same_reference(
    client, campus, make_user
):
    """"chkn puf" must not become an unpriced item that escapes the check -
    that would be the cheapest possible way around the whole system."""
    _, run_headers = await make_user("Runner")
    _, r_headers = await make_user("Requester")
    _, a_headers = await make_admin(client, make_user)
    await price_item(client, a_headers, price=20, lo=15, hi=30, tolerance=20)

    errand = (await place_order(client, r_headers)).json()
    await accept(client, errand["id"], run_headers)

    resp = await client.post(
        f"/fraud/errands/{errand['id']}/claims",
        json={"lines": [{"name": "chkn puf", "unit_price": 45, "quantity": 1}]},
        headers=run_headers,
    )
    assert resp.status_code == 200, resp.text
    claim = resp.json()["claims"][0]
    assert claim["item_key"] == "chicken puff"
    assert claim["verdict"] == "FLAGGED"


async def test_only_the_assigned_runner_may_report_prices(client, campus, make_user):
    _, run_headers = await make_user("Runner")
    _, other_headers = await make_user("Bystander")
    _, r_headers = await make_user("Requester")

    errand = (await place_order(client, r_headers)).json()
    await accept(client, errand["id"], run_headers)

    resp = await client.post(
        f"/fraud/errands/{errand['id']}/claims",
        json={"lines": [{"name": "Chicken Puff", "unit_price": 20, "quantity": 1}]},
        headers=other_headers,
    )
    assert resp.status_code == 403


async def test_the_rupee_line_is_absolute_not_proportional(client, campus, make_user):
    """₹21 over is flagged; ₹19 over is not — regardless of item price."""
    _, run_headers = await make_user("Runner")
    _, r_headers = await make_user("Requester")
    _, a_headers = await make_admin(client, make_user)
    await price_item(client, a_headers, "Masala Tea", 10, 6, 18, tolerance=20)

    errand = (await place_order(client, r_headers, collect=200)).json()
    await accept(client, errand["id"], run_headers)
    resp = await client.post(
        f"/fraud/errands/{errand['id']}/claims",
        json={"lines": [{"name": "Masala Tea", "unit_price": 31, "quantity": 1}]},
        headers=run_headers,
    )
    claim = resp.json()["claims"][0]
    assert claim["verdict"] == "FLAGGED", "₹21 over the ₹10 reference crosses the line"
    assert claim["delta_abs"] == 21.0
    assert resp.json()["withheld"] == 21.0


async def test_walking_the_line_is_flagged_as_a_pattern(client, campus, make_user):
    """The rule that makes a flat threshold hard to game.

    Every claim here is legal — ₹7 over an ₹8 allowance, never once crossing
    it. No money is withheld and no individual claim is fraud. But the runner's
    claims cluster against the line, which is not what real prices do, and the
    pattern gets raised for a human to look at.

    The allowance is 40% of a ₹20 reference, so ₹27 is the most that can be
    claimed without flagging. An earlier version of this test used ₹38, which
    was legal under the flat ₹20 line this replaced.
    """
    runner_id, run_headers = await make_user("Runner")
    _, r_headers = await make_user("Requester")
    _, a_headers = await make_admin(client, make_user)
    for item in ("Chicken Puff", "Veg Puff", "Samosa", "Masala Tea", "Cold Coffee"):
        await price_item(client, a_headers, item, 20, 15, 30, tolerance=20)

    for item in ("Chicken Puff", "Veg Puff", "Samosa", "Masala Tea"):
        errand = (await place_order(client, r_headers, collect=200)).json()
        await accept(client, errand["id"], run_headers)
        resp = await client.post(
            f"/fraud/errands/{errand['id']}/claims",
            json={"lines": [{"name": item, "unit_price": 27, "quantity": 1}]},
            headers=run_headers,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["claims"][0]["verdict"] == "ELEVATED"
        assert body["withheld"] == 0.0, "nothing is withheld — no rule was broken"
        await finish_run(client, errand["id"], run_headers, r_headers)

    async with SessionLocal() as db:
        flags = list(
            await db.scalars(
                select(FraudFlag).where(
                    FraudFlag.user_id == runner_id,
                    FraudFlag.rule == "PERSISTENT_NEAR_THRESHOLD",
                )
            )
        )
    assert len(flags) == 1, "the pattern should be raised exactly once"
    assert flags[0].details["near_line_claims"] == 4
    assert flags[0].details["avg_rupees_over"] == 7.0


async def test_an_honest_runner_near_the_line_once_is_not_flagged(
    client, campus, make_user
):
    """The guard against punishing ordinary price variation: a runner who is
    occasionally a bit over, but usually not, has a low ratio and stays clear."""
    runner_id, run_headers = await make_user("Runner")
    _, r_headers = await make_user("Requester")
    _, a_headers = await make_admin(client, make_user)
    for item in ("Chicken Puff", "Veg Puff", "Samosa", "Masala Tea"):
        await price_item(client, a_headers, item, 20, 15, 30, tolerance=20)

    # One near the line, three at the reference.
    for item, price in [
        ("Chicken Puff", 38),
        ("Veg Puff", 20),
        ("Samosa", 20),
        ("Masala Tea", 21),
    ]:
        errand = (await place_order(client, r_headers, collect=200)).json()
        await accept(client, errand["id"], run_headers)
        await client.post(
            f"/fraud/errands/{errand['id']}/claims",
            json={"lines": [{"name": item, "unit_price": price, "quantity": 1}]},
            headers=run_headers,
        )
        await finish_run(client, errand["id"], run_headers, r_headers)

    async with SessionLocal() as db:
        flags = list(
            await db.scalars(
                select(FraudFlag).where(
                    FraudFlag.user_id == runner_id,
                    FraudFlag.rule == "PERSISTENT_NEAR_THRESHOLD",
                )
            )
        )
    assert flags == [], "occasional variation is not a pattern"


async def test_a_runner_mid_delivery_cannot_place_an_order(client, campus, make_user):
    """The mode lock has to hold at the API, not just in the navbar.

    The frontend redirects order-mode pages while you're carrying a run, but a
    redirect is a courtesy — anyone with devtools or curl goes around it. The
    rule is that an accepted delivery someone is waiting on commits you until
    you finish it or release it back to the queue.
    """
    runner_id, run_headers = await make_user("Runner")
    _, r_headers = await make_user("Requester")

    errand = (await place_order(client, r_headers)).json()
    await accept(client, errand["id"], run_headers)

    blocked = await place_order(client, run_headers, title="Order while running")
    assert blocked.status_code == 409, blocked.text
    assert "before ordering" in blocked.json()["detail"]

    # Releasing the run back to the queue frees them immediately.
    rel = await client.post(f"/errands/{errand['id']}/release", headers=run_headers)
    assert rel.status_code == 200, rel.text

    allowed = await place_order(client, run_headers, title="Order after releasing")
    assert allowed.status_code == 201, allowed.text


async def test_placing_an_order_does_not_stop_you_taking_a_run(client, campus, make_user):
    """The lock is one-directional on purpose — an order you placed commits
    nobody, so it must not stand between you and earning."""
    _, a_headers = await make_user("Orderer")
    _, r_headers = await make_user("Requester")

    await place_order(client, a_headers, title="My own order")
    someone_elses = (await place_order(client, r_headers)).json()

    resp = await client.post(f"/errands/{someone_elses['id']}/accept", headers=a_headers)
    assert resp.status_code == 200, resp.text


# --------------------------------------------------------------- escalation


async def test_one_bad_claim_is_not_punished(client, campus, make_user):
    """A single high claim is a bad day, not a pattern. Nobody is struck for it."""
    runner_id, run_headers = await make_user("Runner")
    _, r_headers = await make_user("Requester")
    _, a_headers = await make_admin(client, make_user)
    await price_item(client, a_headers, price=20, lo=15, hi=30, tolerance=20)

    errand = (await place_order(client, r_headers)).json()
    await accept(client, errand["id"], run_headers)
    await client.post(
        f"/fraud/errands/{errand['id']}/claims",
        json={"lines": [{"name": "Chicken Puff", "unit_price": 45, "quantity": 1}]},
        headers=run_headers,
    )

    async with SessionLocal() as db:
        strikes = list(
            await db.scalars(select(UserStrike).where(UserStrike.user_id == runner_id))
        )
    assert strikes == []

    standing = (await client.get("/fraud/me/standing", headers=run_headers)).json()
    assert standing["flags_in_window"] == 1
    assert standing["next_action_at"] == 3


async def test_many_inflated_lines_on_one_receipt_count_as_one_occasion(
    client, campus, make_user
):
    """Four inflated items on one errand is one act of dishonesty. Counting it
    as four would race someone up the ladder for a single incident."""
    runner_id, run_headers = await make_user("Runner")
    _, r_headers = await make_user("Requester")
    _, a_headers = await make_admin(client, make_user)
    await price_item(client, a_headers, "Chicken Puff", 20, 15, 30)
    await price_item(client, a_headers, "Veg Puff", 15, 10, 25)
    await price_item(client, a_headers, "Masala Tea", 10, 5, 20)

    errand = (await place_order(client, r_headers, collect=500)).json()
    await accept(client, errand["id"], run_headers)
    await client.post(
        f"/fraud/errands/{errand['id']}/claims",
        json={
            "lines": [
                {"name": "Chicken Puff", "unit_price": 45, "quantity": 1},
                {"name": "Veg Puff", "unit_price": 40, "quantity": 1},
                {"name": "Masala Tea", "unit_price": 35, "quantity": 1},
            ]
        },
        headers=run_headers,
    )

    standing = (await client.get("/fraud/me/standing", headers=run_headers)).json()
    assert standing["flags_in_window"] == 1, "one errand, one occasion"
    assert standing["strikes"] == []


async def test_repeated_overcharging_escalates_to_a_strike(client, campus, make_user):
    """Three separate flagged errands is the pattern the ladder waits for."""
    runner_id, run_headers = await make_user("Runner")
    _, r_headers = await make_user("Requester")
    _, a_headers = await make_admin(client, make_user)
    await price_item(client, a_headers, price=20, lo=15, hi=30, tolerance=20)

    for _ in range(3):
        errand = (await place_order(client, r_headers)).json()
        await accept(client, errand["id"], run_headers)
        resp = await client.post(
            f"/fraud/errands/{errand['id']}/claims",
            json={"lines": [{"name": "Chicken Puff", "unit_price": 45, "quantity": 1}]},
            headers=run_headers,
        )
        assert resp.status_code == 200, resp.text
        await finish_run(client, errand["id"], run_headers, r_headers)

    async with SessionLocal() as db:
        strikes = list(
            await db.scalars(select(UserStrike).where(UserStrike.user_id == runner_id))
        )
    assert len(strikes) == 1
    assert strikes[0].level == 1
    assert strikes[0].action == "WARNING"


async def test_a_blocked_runner_cannot_go_online_but_can_go_offline(
    client, campus, make_user
):
    runner_id, run_headers = await make_user("Runner")

    # Put the block in place directly; the ladder that sets it is covered above.
    async with SessionLocal() as db:
        profile = RunnerProfile(user_id=runner_id, campus_id=campus)
        db.add(profile)
        await db.commit()
    from datetime import UTC, datetime, timedelta

    async with SessionLocal() as db:
        await db.execute(
            update(RunnerProfile)
            .where(RunnerProfile.user_id == runner_id)
            .values(fraud_blocked_until=datetime.now(UTC) + timedelta(days=3))
        )
        await db.commit()

    online = await client.post(
        "/runners/me/availability",
        json={"is_available": True, **NEAR},
        headers=run_headers,
    )
    assert online.status_code == 403
    assert "paused" in online.json()["detail"]

    offline = await client.post(
        "/runners/me/availability", json={"is_available": False}, headers=run_headers
    )
    assert offline.status_code == 200


# ------------------------------------------------------------ admin review


async def test_dismissing_a_flag_pays_the_runner_the_withheld_money(
    client, campus, make_user
):
    """The appeal path has to actually move money, or the review is theatre."""
    runner_id, run_headers = await make_user("Runner")
    requester_id, r_headers = await make_user("Requester")
    _, a_headers = await make_admin(client, make_user)
    await price_item(client, a_headers, price=20, lo=15, hi=30, tolerance=20)
    await set_balance(runner_id, "0")

    errand = (await place_order(client, r_headers, reward=30, collect=100)).json()
    await accept(client, errand["id"], run_headers)
    await client.post(
        f"/fraud/errands/{errand['id']}/claims",
        json={"lines": [{"name": "Chicken Puff", "unit_price": 45, "quantity": 2}]},
        headers=run_headers,
    )
    await settle(errand["id"], runner_id, reward=30, collect=100)
    assert await balance_of(runner_id) == Decimal("70.00")

    flags = (await client.get("/fraud/flags", headers=a_headers)).json()
    flag = next(f for f in flags if f["user_id"] == str(runner_id))

    resp = await client.post(
        f"/fraud/flags/{flag['id']}/review",
        json={"uphold": False, "note": "Receipt checked out."},
        headers=a_headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "DISMISSED"

    # The 50 that was held back is now theirs.
    assert await balance_of(runner_id) == Decimal("120.00")

    # And the claim counts as honest evidence again.
    async with SessionLocal() as db:
        claim = await db.scalar(
            select(RunnerPriceClaim).where(
                RunnerPriceClaim.errand_id == uuid.UUID(errand["id"])
            )
        )
    assert claim.verdict == "OK"


async def test_upholding_a_flag_returns_the_money_to_the_requester(
    client, campus, make_user
):
    runner_id, run_headers = await make_user("Runner")
    requester_id, r_headers = await make_user("Requester")
    _, a_headers = await make_admin(client, make_user)
    await price_item(client, a_headers, price=20, lo=15, hi=30, tolerance=20)
    await set_balance(requester_id, "500")
    await set_balance(runner_id, "0")

    errand = (await place_order(client, r_headers, reward=30, collect=100)).json()
    await accept(client, errand["id"], run_headers)
    await client.post(
        f"/fraud/errands/{errand['id']}/claims",
        json={"lines": [{"name": "Chicken Puff", "unit_price": 45, "quantity": 2}]},
        headers=run_headers,
    )
    await settle(errand["id"], runner_id, reward=30, collect=100)

    before = await balance_of(requester_id)
    flags = (await client.get("/fraud/flags", headers=a_headers)).json()
    flag = next(f for f in flags if f["user_id"] == str(runner_id))
    await client.post(
        f"/fraud/flags/{flag['id']}/review", json={"uphold": True}, headers=a_headers
    )

    assert await balance_of(requester_id) == before + Decimal("50.00")
    assert await balance_of(runner_id) == Decimal("70.00")


# ------------------------------------------------------- reference upkeep


async def test_admin_must_price_an_item_before_anyone_can_be_flagged(
    client, campus, make_user
):
    _, a_headers = await make_admin(client, make_user)
    # A name nobody has priced before - reference prices outlive a test run,
    # so asserting on a fixed name would pass once and fail on every re-run.
    name = f"Cold Coffee {uuid.uuid4().hex[:6]}"
    refs = (await client.get("/fraud/references", headers=a_headers)).json()
    assert all(r["display_name"] != name for r in refs)

    created = await price_item(client, a_headers, name, 50, 40, 70)
    assert created["item_key"] == name.lower()
    assert created["source"] == "ADMIN"


async def test_reference_endpoints_are_admin_only(client, campus, make_user):
    _, headers = await make_user("Ordinary Student")
    assert (await client.get("/fraud/references", headers=headers)).status_code == 403
    assert (await client.get("/fraud/flags", headers=headers)).status_code == 403
    resp = await client.post(
        "/fraud/references",
        json={
            "display_name": "Sneaky Item",
            "reference_price": 5,
            "band_min": 1,
            "band_max": 10,
        },
        headers=headers,
    )
    assert resp.status_code == 403


async def test_a_reference_cannot_be_set_outside_its_own_band(client, campus, make_user):
    _, a_headers = await make_admin(client, make_user)
    resp = await client.post(
        "/fraud/references",
        json={
            "display_name": "Impossible Item",
            "reference_price": 99,
            "band_min": 10,
            "band_max": 20,
        },
        headers=a_headers,
    )
    assert resp.status_code == 422


# ------------------------------------------------------------- item aliases


async def test_a_pending_alias_changes_nothing(client, campus, make_user):
    """The safety property the whole design rests on.

    An alias applied automatically would let a runner mint a spelling, have it
    attached to a cheap item, and be reimbursed against the wrong reference.
    Until an admin agrees, a suggestion must be inert.
    """
    _, run_headers = await make_user("Runner")
    _, r_headers = await make_user("Requester")
    _, a_headers = await make_admin(client, make_user)
    await price_item(client, a_headers, "Chicken Puff", 20, 15, 30, tolerance=20)

    # Unique per run: alias rows are campus-scoped and outlive the test.
    raw_name = f"Chicken Pattie {uuid.uuid4().hex[:6]}"
    async with SessionLocal() as db:
        db.add(
            ItemAlias(
                campus_id=campus,
                alias_key=normalize(raw_name),
                item_key="chicken puff",
                sample_raw_name=raw_name,
                source="MODEL",
                status="PENDING",
            )
        )
        await db.commit()

    errand = (await place_order(client, r_headers, collect=200)).json()
    await accept(client, errand["id"], run_headers)
    resp = await client.post(
        f"/fraud/errands/{errand['id']}/claims",
        json={"lines": [{"name": raw_name, "unit_price": 90, "quantity": 1}]},
        headers=run_headers,
    )
    claim = resp.json()["claims"][0]
    assert claim["verdict"] == "NO_REFERENCE", "a pending alias must not price anything"
    assert resp.json()["withheld"] == 0.0


async def test_approving_an_alias_makes_it_bite(client, campus, make_user):
    """And the other half: once a human agrees, the same claim is checked."""
    _, run_headers = await make_user("Runner")
    _, r_headers = await make_user("Requester")
    _, a_headers = await make_admin(client, make_user)
    await price_item(client, a_headers, "Chicken Puff", 20, 15, 30, tolerance=20)

    raw_name = f"Chicken Turnover {uuid.uuid4().hex[:6]}"
    async with SessionLocal() as db:
        row = ItemAlias(
            campus_id=campus,
            alias_key=normalize(raw_name),
            item_key="chicken puff",
            sample_raw_name=raw_name,
            source="MODEL",
            status="PENDING",
        )
        db.add(row)
        await db.commit()
        alias_id = str(row.id)

    listed = (await client.get("/fraud/aliases", headers=a_headers)).json()
    assert any(a["id"] == alias_id for a in listed)

    decided = await client.post(
        f"/fraud/aliases/{alias_id}/decide", params={"approve": True}, headers=a_headers
    )
    assert decided.status_code == 200, decided.text
    assert decided.json()["status"] == "APPROVED"

    errand = (await place_order(client, r_headers, collect=200)).json()
    await accept(client, errand["id"], run_headers)
    resp = await client.post(
        f"/fraud/errands/{errand['id']}/claims",
        json={"lines": [{"name": raw_name, "unit_price": 90, "quantity": 1}]},
        headers=run_headers,
    )
    claim = resp.json()["claims"][0]
    assert claim["item_key"] == "chicken puff"
    assert claim["verdict"] == "FLAGGED", "now judged against the puff it actually is"


async def test_alias_endpoints_are_admin_only(client, campus, make_user):
    _, headers = await make_user("Ordinary Student")
    assert (await client.get("/fraud/aliases", headers=headers)).status_code == 403
    assert (await client.post("/fraud/aliases/sweep", headers=headers)).status_code == 403


async def test_an_alias_cannot_be_decided_twice(client, campus, make_user):
    _, a_headers = await make_admin(client, make_user)
    async with SessionLocal() as db:
        raw_name = f"Iced Latte {uuid.uuid4().hex[:6]}"
        row = ItemAlias(
            campus_id=campus,
            alias_key=normalize(raw_name),
            item_key="cold coffee",
            sample_raw_name=raw_name,
            source="MODEL",
            status="PENDING",
        )
        db.add(row)
        await db.commit()
        alias_id = str(row.id)

    first = await client.post(
        f"/fraud/aliases/{alias_id}/decide", params={"approve": False}, headers=a_headers
    )
    assert first.status_code == 200
    again = await client.post(
        f"/fraud/aliases/{alias_id}/decide", params={"approve": True}, headers=a_headers
    )
    assert again.status_code == 409
