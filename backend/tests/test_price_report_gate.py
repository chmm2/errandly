"""Prices are reported before pickup, and the endpoint enforces it.

A disabled button is not a rule. The runner's client is the easiest thing in
the system to bypass, and the whole reference-price mechanism rests on there
being a per-item report to judge - so the refusal lives on the endpoint and the
button merely reflects it.
"""

import uuid
from decimal import Decimal

import pytest
from sqlalchemy import update

from app.core.database import SessionLocal
from app.modules.auth.models import User
from app.modules.ledger import service as ledger

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


async def _admin(make_user):
    admin_id, headers = await make_user("Price Admin")
    async with SessionLocal() as db:
        await db.execute(update(User).where(User.id == admin_id).values(role="ADMIN"))
        await db.commit()
    return headers


async def _price(client, admin_headers, name, price, lo, hi):
    body = {
        "display_name": name,
        "reference_price": price,
        "band_min": lo,
        "band_max": hi,
        "tolerance_abs": 20,
    }
    resp = await client.post("/fraud/references", json=body, headers=admin_headers)
    if resp.status_code == 201:
        return resp.json()
    existing = (await client.get("/fraud/references", headers=admin_headers)).json()
    match = next(r for r in existing if r["display_name"] == name)
    patched = await client.patch(
        f"/fraud/references/{match['id']}", json=body, headers=admin_headers
    )
    return patched.json()


async def _shopping_run(client, r_headers, run_headers, lines):
    errand = (
        await client.post(
            "/errands",
            json={
                "category": "GROCERY",
                "title": "Canteen run",
                "pickup_label": "Canteen",
                "drop_lat": NEAR["lat"],
                "drop_lng": NEAR["lng"],
                "reward": 20,
                "list_items": lines,
            },
            headers=r_headers,
        )
    ).json()
    accepted = await client.post(
        f"/errands/{errand['id']}/accept", headers=run_headers
    )
    assert accepted.status_code == 200, accepted.text
    return errand


async def test_pickup_is_refused_until_prices_are_reported(
    client, campus, make_user
):
    admin_headers = await _admin(make_user)
    ref = await _price(client, admin_headers, "Chicken Puff", 25, 15, 40)

    requester_id, r_headers = await make_user("Requester")
    _, run_headers = await make_user("Runner")
    await _fund(requester_id, "1000")

    errand = await _shopping_run(
        client, r_headers, run_headers,
        [{"name": "Chicken Puff", "quantity": 2, "reference_id": ref["id"]}],
    )

    early = await client.post(f"/errands/{errand['id']}/pickup", headers=run_headers)
    assert early.status_code == 409, early.text
    assert "report" in early.json()["detail"].lower()

    reported = await client.post(
        f"/fraud/errands/{errand['id']}/claims",
        json={"lines": [{"name": "Chicken Puff", "unit_price": 25, "quantity": 2}]},
        headers=run_headers,
    )
    assert reported.status_code == 200, reported.text

    now = await client.post(f"/errands/{errand['id']}/pickup", headers=run_headers)
    assert now.status_code == 200, now.text
    assert now.json()["status"] == "IN_PROGRESS"


async def test_the_flag_matches_the_endpoint(client, campus, make_user):
    """The button reads this. If it disagreed with the guard, the runner would
    be shown a control that fails when pressed."""
    admin_headers = await _admin(make_user)
    ref = await _price(client, admin_headers, "Masala Tea", 15, 10, 25)

    requester_id, r_headers = await make_user("Requester")
    _, run_headers = await make_user("Runner")
    await _fund(requester_id, "1000")

    errand = await _shopping_run(
        client, r_headers, run_headers,
        [{"name": "Masala Tea", "quantity": 1, "reference_id": ref["id"]}],
    )

    before = (await client.get(f"/errands/{errand['id']}", headers=run_headers)).json()
    assert before["price_report_pending"] is True

    await client.post(
        f"/fraud/errands/{errand['id']}/claims",
        json={"lines": [{"name": "Masala Tea", "unit_price": 15, "quantity": 1}]},
        headers=run_headers,
    )

    after = (await client.get(f"/errands/{errand['id']}", headers=run_headers)).json()
    assert after["price_report_pending"] is False


async def test_an_errand_with_nothing_to_price_is_not_gated(
    client, campus, make_user
):
    """A gate pickup has no lines to report. Demanding a report would block a
    runner on a question the errand cannot answer."""
    requester_id, r_headers = await make_user("Requester")
    _, run_headers = await make_user("Runner")
    await _fund(requester_id, "1000")

    errand = (
        await client.post(
            "/errands",
            json={
                "category": "CUSTOM",
                "title": "Collect from the gate",
                "pickup_label": "Main Gate",
                "drop_lat": NEAR["lat"],
                "drop_lng": NEAR["lng"],
                "reward": 30,
                "collect_amount": 200,
            },
            headers=r_headers,
        )
    ).json()
    await client.post(f"/errands/{errand['id']}/accept", headers=run_headers)

    detail = (await client.get(f"/errands/{errand['id']}", headers=run_headers)).json()
    assert detail["price_report_pending"] is False

    resp = await client.post(f"/errands/{errand['id']}/pickup", headers=run_headers)
    assert resp.status_code == 200, resp.text
