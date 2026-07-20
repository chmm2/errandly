"""Escrow holds + tamper-evident hash-chained ledger."""
import uuid

import pytest
from sqlalchemy import func, select, text

from app.core.database import SessionLocal
from app.modules.auth.models import User
from app.modules.ledger import service as ledger_service
from app.modules.ledger.models import EXTERNAL_ACCOUNT, EscrowHold, LedgerEntry
from app.workers.consumers import handle_settlement
from tests.test_sprint5 import add_item, make_vendor, open_store, promote

pytestmark = pytest.mark.asyncio(loop_scope="session")

NEAR = {"lat": 12.9692, "lng": 79.1559}


def completed_event(errand: dict, runner_id: uuid.UUID) -> dict:
    return {
        "event_id": str(uuid.uuid4()),
        "event_type": "ORDER_COMPLETED",
        "aggregate_type": "errand",
        "aggregate_id": errand["id"],
        "occurred_at": "2026-07-20T10:00:00+00:00",
        "payload": {
            "errand_id": errand["id"],
            "campus_id": errand["campus_id"],
            "requester_id": errand["requester_id"],
            "runner_id": str(runner_id),
            "status": "COMPLETED",
            "title": errand["title"],
            "category": errand["category"],
            "reward": errand["reward"],
            "collect_amount": errand["collect_amount"],
        },
    }


async def wallet_balance(headers, client) -> float:
    return (await client.get("/ledger/wallet", headers=headers)).json()["balance"]


async def errand_entry_sum(errand_id: str) -> float:
    async with SessionLocal() as db:
        total = await db.scalar(
            select(func.coalesce(func.sum(LedgerEntry.amount), 0)).where(
                LedgerEntry.errand_id == uuid.UUID(errand_id)
            )
        )
    return round(float(total), 2)


# ------------------------------------------------------------- hold on post

async def test_post_holds_funds_and_underfunded_is_rejected(client, make_user):
    requester_id, requester = await make_user("Buyer")
    before = await wallet_balance(requester, client)

    order = await client.post(
        "/errands",
        json={
            "category": "CUSTOM", "title": "Parcel from gate", "pickup_label": "Gate",
            "drop_lat": NEAR["lat"], "drop_lng": NEAR["lng"], "reward": 30, "collect_amount": 200,
        },
        headers=requester,
    )
    assert order.status_code == 201, order.text
    body = order.json()
    hold = body["escrow"]
    assert hold["status"] == "HELD"
    assert hold["item_total"] == 200
    assert hold["total"] == round(200 + hold["runner_fee"] + hold["convenience_fee"], 2)

    after = await wallet_balance(requester, client)
    assert round(before - after, 2) == hold["total"]  # exactly the held total left the wallet
    assert await errand_entry_sum(body["id"]) == 0.0  # hold pair nets to zero

    # drain the wallet, then a new post must be refused with 402
    async with SessionLocal() as db:
        campus_id = (await db.get(User, requester_id)).campus_id
        bal = await ledger_service.account_balance(db, campus_id, requester_id)
        await ledger_service.append_entry(db, campus_id, requester_id, "TOPUP", -bal)
        await ledger_service.append_entry(db, campus_id, EXTERNAL_ACCOUNT, "TOPUP", bal)
        await db.commit()

    broke = await client.post(
        "/errands",
        json={
            "category": "CUSTOM", "title": "Too pricey", "pickup_label": "Gate",
            "drop_lat": NEAR["lat"], "drop_lng": NEAR["lng"], "reward": 30, "collect_amount": 500,
        },
        headers=requester,
    )
    assert broke.status_code == 402, broke.text
    assert "wallet" in broke.json()["detail"].lower()


# ------------------------------------- release with per-item reconciliation

async def test_release_splits_and_refunds_unavailable_item(client, make_user):
    vendor, vendor_headers = await make_vendor(client, make_user, "Reco Canteen")
    await open_store(client, vendor_headers)
    roll = await add_item(client, vendor_headers, "Veg Roll", 40)
    juice = await add_item(client, vendor_headers, "Juice", 25, section="Drinks")

    requester_id, requester = await make_user("Hungry")
    runner_id, runner = await make_user("Runner")

    order = await client.post(
        "/errands",
        json={
            "category": "FOOD", "vendor_id": vendor["id"],
            "items": [
                {"menu_item_id": roll["id"], "quantity": 2},   # 80
                {"menu_item_id": juice["id"], "quantity": 1},  # 25
            ],
            "title": "Lunch", "pickup_label": "Reco Canteen",
            "drop_lat": NEAR["lat"], "drop_lng": NEAR["lng"], "reward": 30,
        },
        headers=requester,
    )
    assert order.status_code == 201, order.text
    body = order.json()
    eid = body["id"]
    item_total = body["escrow"]["item_total"]
    assert item_total == 105
    fee = body["escrow"]["runner_fee"]  # base + tip

    r_before = await wallet_balance(requester, client)

    await client.post(f"/errands/{eid}/accept", headers=runner)
    await client.post(f"/errands/{eid}/pickup", headers=runner)
    # runner marks the juice out of stock — its ₹25 must come back to the buyer
    juice_line = next(i for i in body["items"] if i["name_snapshot"] == "Juice")
    await client.post(
        f"/errands/{eid}/items/{juice_line['id']}/availability",
        json={"available": False}, headers=runner,
    )
    await client.post(f"/errands/{eid}/deliver", headers=runner)
    await client.post(f"/errands/{eid}/complete", headers=requester)

    async with SessionLocal() as db:
        await handle_settlement(db, completed_event(body, runner_id))
        await db.commit()

    # runner: fee + reimbursement of AVAILABLE items only (2 rolls = 80)
    async with SessionLocal() as db:
        payouts = list(
            await db.scalars(
                select(LedgerEntry).where(
                    LedgerEntry.account_id == runner_id,
                    LedgerEntry.errand_id == uuid.UUID(eid),
                )
            )
        )
        hold = await db.get(EscrowHold, uuid.UUID(eid))
    by_type = {e.entry_type: float(e.amount) for e in payouts}
    assert by_type["REIMBURSEMENT"] == 80
    assert by_type["REWARD"] == fee
    assert hold.status == "RELEASED"

    # buyer got the ₹25 for the sold-out juice back
    r_after = await wallet_balance(requester, client)
    assert round(r_after - r_before, 2) == 25.0
    assert await errand_entry_sum(eid) == 0.0  # every leg still balances


# ------------------------------------------------------------ cancel refund

async def test_cancel_refunds_the_hold(client, make_user):
    requester_id, requester = await make_user("Canceller")
    before = await wallet_balance(requester, client)
    order = await client.post(
        "/errands",
        json={
            "category": "CUSTOM", "title": "Never mind", "pickup_label": "Gate",
            "drop_lat": NEAR["lat"], "drop_lng": NEAR["lng"], "reward": 25, "collect_amount": 150,
        },
        headers=requester,
    )
    eid = order.json()["id"]
    assert await wallet_balance(requester, client) < before  # money is held

    cancel = await client.post(f"/errands/{eid}/cancel", headers=requester)
    assert cancel.status_code == 200, cancel.text

    assert await wallet_balance(requester, client) == before  # fully refunded
    async with SessionLocal() as db:
        hold = await db.get(EscrowHold, uuid.UUID(eid))
    assert hold.status == "REFUNDED"
    assert await errand_entry_sum(eid) == 0.0


# ----------------------------------------------------- tamper-evident chain

async def test_verify_detects_tampering(client, make_user):
    admin_id, admin = await make_user("Auditor")
    await promote(admin_id, "ADMIN")

    intact = (await client.get("/ledger/verify", headers=admin)).json()
    assert intact["intact"] is True, intact
    assert intact["broken_seq"] is None

    # tamper: bump an amount directly in the DB (as an attacker with SQL access)
    async with SessionLocal() as db:
        campus_id = (await db.get(User, admin_id)).campus_id
        row = (
            await db.execute(
                select(LedgerEntry.id, LedgerEntry.seq, LedgerEntry.amount)
                .where(LedgerEntry.campus_id == campus_id)
                .order_by(LedgerEntry.seq.asc())
                .limit(1)
            )
        ).first()
        original = row.amount
        await db.execute(
            text("UPDATE ledger_entries SET amount = amount + 1 WHERE id = :id"),
            {"id": str(row.id)},
        )
        await db.commit()

    broken = (await client.get("/ledger/verify", headers=admin)).json()
    assert broken["intact"] is False
    assert broken["broken_seq"] == row.seq
    assert "alter" in broken["reason"].lower()

    # restore so the shared chain is clean for other tests
    async with SessionLocal() as db:
        await db.execute(
            text("UPDATE ledger_entries SET amount = :a WHERE id = :id"),
            {"a": original, "id": str(row.id)},
        )
        await db.commit()
    healed = (await client.get("/ledger/verify", headers=admin)).json()
    assert healed["intact"] is True
