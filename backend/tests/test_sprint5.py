import uuid

import pytest
from sqlalchemy import select, update

from app.core.database import SessionLocal
from app.modules.auth.models import User
from app.modules.ledger.models import LedgerEntry
from app.workers.consumers import already_processed, handle_settlement

pytestmark = pytest.mark.asyncio(loop_scope="session")

NEAR = {"lat": 12.9692, "lng": 79.1559}


async def promote(user_id: uuid.UUID, role: str) -> None:
    async with SessionLocal() as db:
        await db.execute(update(User).where(User.id == user_id).values(role=role))
        await db.commit()


async def make_vendor(client, make_user, name="Test Canteen"):
    """Admin onboards a vendor; returns (vendor_dict, vendor_headers)."""
    admin_id, admin_headers = await make_user("Admin")
    await promote(admin_id, "ADMIN")
    email = f"vendor_{uuid.uuid4().hex[:10]}@errandlyvendors.in"
    resp = await client.post(
        "/vendors/onboard",
        json={
            "name": name,
            "category": "FOOD",
            "owner_email": email,
            "owner_display_name": "Canteen Owner",
            "owner_password": "vendorpass123",
        },
        headers=admin_headers,
    )
    assert resp.status_code == 201, resp.text
    login = await client.post(
        "/auth/login", json={"email": email, "password": "vendorpass123"}
    )
    assert login.status_code == 200, login.text
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    return resp.json(), headers


async def add_item(client, vendor_headers, name="Veg Roll", price=40, section="Rolls"):
    resp = await client.post(
        "/vendors/me/menu-items",
        json={"section": section, "name": name, "price": price},
        headers=vendor_headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def open_store(client, vendor_headers):
    resp = await client.patch(
        "/vendors/me", json={"is_open": True}, headers=vendor_headers
    )
    assert resp.status_code == 200, resp.text


def order_payload(vendor_id, items, **overrides):
    payload = {
        "category": "FOOD",
        "vendor_id": vendor_id,
        "items": items,
        "title": "Canteen order",
        "pickup_label": "Test Canteen",
        "drop_lat": NEAR["lat"],
        "drop_lng": NEAR["lng"],
        "reward": 20,
    }
    payload.update(overrides)
    return payload


# ------------------------------------------------------------------------ RBAC

async def test_rbac_and_ownership(client, make_user):
    _, student = await make_user("Student")

    # students can't onboard vendors or use the portal
    onboard = await client.post(
        "/vendors/onboard",
        json={
            "name": "Nope", "category": "FOOD", "owner_email": "x@errandlyvendors.in",
            "owner_display_name": "X", "owner_password": "password123",
        },
        headers=student,
    )
    assert onboard.status_code == 403
    assert (await client.get("/vendors/me", headers=student)).status_code == 403

    # vendor A cannot edit vendor B's items (ownership, not just role)
    _, vendor_a = await make_vendor(client, make_user, "Store A")
    _, vendor_b = await make_vendor(client, make_user, "Store B")
    item_b = await add_item(client, vendor_b, "B's samosa")
    stolen = await client.patch(
        f"/vendors/me/menu-items/{item_b['id']}", json={"price": 1}, headers=vendor_a
    )
    assert stolen.status_code == 404  # not yours ⇒ effectively doesn't exist


# ------------------------------------------------- cache invalidation on write

async def test_sold_out_toggle_shows_instantly(client, make_user):
    vendor, vendor_headers = await make_vendor(client, make_user)
    _, student = await make_user("Hungry Student")
    item = await add_item(client, vendor_headers, "Maggi", 35)

    # first read populates the cache
    menu1 = (await client.get(f"/vendors/{vendor['id']}/menu", headers=student)).json()
    assert menu1["items"][0]["is_available"] is True

    # vendor flips sold out — cache must be busted, not waited out (TTL is 5min)
    toggle = await client.patch(
        f"/vendors/me/menu-items/{item['id']}",
        json={"is_available": False},
        headers=vendor_headers,
    )
    assert toggle.status_code == 200

    menu2 = (await client.get(f"/vendors/{vendor['id']}/menu", headers=student)).json()
    assert menu2["items"][0]["is_available"] is False  # instantly


# --------------------------------------------------- order-time revalidation

async def test_order_revalidation_and_snapshots(client, make_user):
    vendor, vendor_headers = await make_vendor(client, make_user)
    _, student = await make_user("Buyer")
    roll = await add_item(client, vendor_headers, "Veg Roll", 40)
    juice = await add_item(client, vendor_headers, "Juice", 25, section="Drinks")

    # closed store → refused
    closed = await client.post(
        "/errands",
        json=order_payload(vendor["id"], [{"menu_item_id": roll["id"], "quantity": 2}]),
        headers=student,
    )
    assert closed.status_code == 409
    assert "closed" in closed.json()["detail"]

    await open_store(client, vendor_headers)

    # happy path: items snapshotted + totalled server-side
    order = await client.post(
        "/errands",
        json=order_payload(
            vendor["id"],
            [
                {"menu_item_id": roll["id"], "quantity": 2},
                {"menu_item_id": juice["id"], "quantity": 1},
            ],
        ),
        headers=student,
    )
    assert order.status_code == 201, order.text
    body = order.json()
    assert body["items_total"] == 2 * 40 + 25
    assert {i["name_snapshot"] for i in body["items"]} == {"Veg Roll", "Juice"}

    # sold-out item → 409 with a diff the UI can show
    await client.patch(
        f"/vendors/me/menu-items/{roll['id']}",
        json={"is_available": False},
        headers=vendor_headers,
    )
    stale = await client.post(
        "/errands",
        json=order_payload(vendor["id"], [{"menu_item_id": roll["id"], "quantity": 1}]),
        headers=student,
    )
    assert stale.status_code == 409
    assert "sold out" in stale.json()["detail"]

    # price change later never rewrites the placed order (snapshot vs reference)
    await client.patch(
        f"/vendors/me/menu-items/{juice['id']}", json={"price": 99}, headers=vendor_headers
    )
    detail = (await client.get(f"/errands/{body['id']}", headers=student)).json()
    juice_line = next(i for i in detail["items"] if i["name_snapshot"] == "Juice")
    assert juice_line["unit_price_snapshot"] == 25


# ---------------------------------------------------------- settlement ledger

async def test_settlement_idempotent_and_earnings(client, make_user, campus):
    runner_id, runner_headers = await make_user("Paid Runner")
    event = {
        "event_id": str(uuid.uuid4()),
        "event_type": "ORDER_COMPLETED",
        "aggregate_type": "errand",
        "aggregate_id": str(uuid.uuid4()),
        "occurred_at": "2026-07-12T10:00:00+00:00",
        "payload": {
            "errand_id": None,  # ledger allows null errand ref
            "campus_id": str(campus),
            "requester_id": str(uuid.uuid4()),
            "runner_id": str(runner_id),
            "status": "COMPLETED",
            "title": "Settlement test",
            "category": "CUSTOM",
            "reward": 45.0,
            "collect_amount": 250.0,
        },
    }
    # settlement needs an errand_id-free path: fake a uuid errand? FK requires
    # a real errand — create one instead.
    _, requester = await make_user("Requester")
    errand = (
        await client.post(
            "/errands",
            json={
                "category": "CUSTOM", "title": "Settlement test",
                "pickup_label": "Gate", "drop_lat": NEAR["lat"],
                "drop_lng": NEAR["lng"], "reward": 45, "collect_amount": 250,
            },
            headers=requester,
        )
    ).json()
    event["payload"]["errand_id"] = errand["id"]

    async with SessionLocal() as db:
        assert not await already_processed(db, "settlement-service", uuid.UUID(event["event_id"]))
        await handle_settlement(db, event)
        await db.commit()

    # redelivery: gate blocks the double payout
    async with SessionLocal() as db:
        assert await already_processed(db, "settlement-service", uuid.UUID(event["event_id"]))
        await db.commit()

    async with SessionLocal() as db:
        entries = list(
            await db.scalars(select(LedgerEntry).where(LedgerEntry.user_id == runner_id))
        )
    # TOPUP is wallet funding from the fixture, not a payout - this test is
    # about what settlement paid out, so judge only the payout types.
    payouts = [e for e in entries if e.entry_type != "TOPUP"]
    assert sorted(e.entry_type for e in payouts) == ["REIMBURSEMENT", "REWARD"]
    assert sum(float(e.amount) for e in payouts) == 295.0

    earnings = (await client.get("/ledger/me", headers=runner_headers)).json()
    assert earnings["balance"] == 295.0
    assert earnings["week_total"] == 295.0
    assert earnings["week_runs"] == 1


# ------------------------------------------------------------------- ratings

async def test_rating_updates_reputation(client, make_user):
    _, requester = await make_user("Requester")
    runner_id, runner = await make_user("Rated Runner")
    errand = (
        await client.post(
            "/errands",
            json={
                "category": "FOOD", "title": "Rate me", "pickup_label": "Canteen",
                "drop_lat": NEAR["lat"], "drop_lng": NEAR["lng"], "reward": 20,
            },
            headers=requester,
        )
    ).json()
    eid = errand["id"]

    # can't rate before completion
    early = await client.post(f"/errands/{eid}/rate", json={"stars": 5}, headers=requester)
    assert early.status_code == 409

    await client.post(f"/errands/{eid}/accept", headers=runner)
    await client.post(f"/errands/{eid}/pickup", json={"amount_spent": 0}, headers=runner)
    await client.post(f"/errands/{eid}/deliver", headers=runner)
    await client.post(f"/errands/{eid}/complete", headers=requester)

    rated = await client.post(
        f"/errands/{eid}/rate", json={"stars": 4, "comment": "quick!"}, headers=requester
    )
    assert rated.status_code == 204, rated.text

    async with SessionLocal() as db:
        runner_user = await db.get(User, runner_id)
        # fresh account: count 0, score 5.00 → first real rating replaces it
        assert runner_user.rating_count == 1
        assert float(runner_user.reputation_score) == 4.0

    # one rating per errand
    again = await client.post(f"/errands/{eid}/rate", json={"stars": 1}, headers=requester)
    assert again.status_code == 409
