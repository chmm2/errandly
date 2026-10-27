"""Headroom is charged on non-MRP goods and on nothing else.

An MRP packet carries its price printed on it and a stated cash amount is
exact, so there is nothing to discover at the counter and nothing to pad.
A loose-priced canteen item is the opposite: what it actually costs is found
out with the runner's own money already spent. Only that gets headroom.
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
PCT = Decimal(str(settings.escrow_buffer_pct))


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


async def _hold(errand_id) -> EscrowHold:
    async with SessionLocal() as db:
        return await db.get(EscrowHold, uuid.UUID(str(errand_id)))


async def _admin(make_user):
    admin_id, headers = await make_user("Price Admin")
    async with SessionLocal() as db:
        await db.execute(update(User).where(User.id == admin_id).values(role="ADMIN"))
        await db.commit()
    return headers


async def _price(client, admin_headers, name, price, lo, hi):
    """Upsert a reference price. The campus outlives any one test."""
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
    assert resp.status_code == 409, resp.text
    existing = (await client.get("/fraud/references", headers=admin_headers)).json()
    match = next(r for r in existing if r["display_name"] == name)
    patched = await client.patch(
        f"/fraud/references/{match['id']}", json=body, headers=admin_headers
    )
    assert patched.status_code == 200, patched.text
    return patched.json()


async def _shopping(client, headers, lines, reward=30):
    return await client.post(
        "/errands",
        json={
            "category": "GROCERY",
            "title": "Canteen run",
            "pickup_label": "Canteen",
            "drop_lat": NEAR["lat"],
            "drop_lng": NEAR["lng"],
            "reward": reward,
            "list_items": lines,
        },
        headers=headers,
    )


# ------------------------------------------------------------ the arithmetic


async def test_a_non_mrp_line_is_priced_and_padded(client, campus, make_user):
    """Four puffs at the campus price of 25, plus 16% headroom, plus the fee."""
    admin_headers = await _admin(make_user)
    ref = await _price(client, admin_headers, "Chicken Puff", 25, 15, 40)

    requester_id, headers = await make_user("Requester")
    await _fund(requester_id, "1000")

    resp = await _shopping(
        client, headers,
        [{"name": "Chicken Puff", "quantity": 4, "reference_id": ref["id"]}],
    )
    assert resp.status_code == 201, resp.text
    errand = resp.json()

    hold = await _hold(errand["id"])
    assert Decimal(str(hold.items_total)) == Decimal("100.00"), "4 x 25"
    assert Decimal(str(hold.buffer_base)) == Decimal("100.00")
    assert Decimal(str(hold.buffer)) == Decimal("16.00"), "16% of 100"
    assert Decimal(str(hold.amount)) == Decimal("146.00"), "100 + 16 + 30 fee"
    assert await _balance(requester_id) == Decimal("854.00")


async def test_an_unpriced_line_earns_no_headroom(client, campus, make_user):
    """Nobody has priced it, so there is no number to take a percentage of."""
    requester_id, headers = await make_user("Requester")
    await _fund(requester_id, "1000")

    resp = await _shopping(client, headers, [{"name": "Something odd", "quantity": 2}])
    assert resp.status_code == 201, resp.text

    hold = await _hold(resp.json()["id"])
    assert Decimal(str(hold.buffer_base)) == Decimal("0.00")
    assert Decimal(str(hold.buffer)) == Decimal("0.00")
    assert Decimal(str(hold.amount)) == Decimal("30.00"), "the fee alone"


async def test_stated_cash_is_exact(client, campus, make_user):
    """A gate pickup names an exact amount. Padding it would lock money that
    no outcome could ever need."""
    requester_id, headers = await make_user("Requester")
    await _fund(requester_id, "1000")

    resp = await client.post(
        "/errands",
        json={
            "category": "CUSTOM",
            "title": "Collect from the gate",
            "pickup_label": "Main Gate",
            "drop_lat": NEAR["lat"],
            "drop_lng": NEAR["lng"],
            "reward": 30,
            "collect_amount": 300,
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text

    hold = await _hold(resp.json()["id"])
    assert Decimal(str(hold.buffer)) == Decimal("0.00"), "MRP/stated cash is exact"
    assert Decimal(str(hold.amount)) == Decimal("330.00"), "300 + 30, no padding"


async def test_a_mixed_basket_pads_only_the_loose_part(client, campus, make_user):
    admin_headers = await _admin(make_user)
    ref = await _price(client, admin_headers, "Masala Tea", 15, 10, 25)

    requester_id, headers = await make_user("Requester")
    await _fund(requester_id, "1000")

    resp = await _shopping(
        client, headers,
        [
            {"name": "Masala Tea", "quantity": 2, "reference_id": ref["id"]},
            {"name": "Sealed biscuit packet", "quantity": 1},
        ],
    )
    assert resp.status_code == 201, resp.text

    hold = await _hold(resp.json()["id"])
    assert Decimal(str(hold.buffer_base)) == Decimal("30.00"), "the tea only"
    assert Decimal(str(hold.buffer)) == Decimal("4.80"), "16% of 30"
    assert Decimal(str(hold.amount)) == Decimal("64.80"), "30 + 4.80 + 30 fee"


# ------------------------------------------------------------------ safety


async def test_the_client_cannot_set_the_price(client, campus, make_user):
    """Only the id travels; the server reprices from its own row. A request
    body that tries to name an amount must not change what is held."""
    admin_headers = await _admin(make_user)
    ref = await _price(client, admin_headers, "Veg Puff", 20, 12, 30)

    requester_id, headers = await make_user("Requester")
    await _fund(requester_id, "1000")

    resp = await _shopping(
        client, headers,
        [{
            "name": "Totally different name",
            "quantity": 1,
            "reference_id": ref["id"],
            "unit_price": 999,
            "reference_price": 999,
        }],
    )
    assert resp.status_code == 201, resp.text

    hold = await _hold(resp.json()["id"])
    assert Decimal(str(hold.items_total)) == Decimal("20.00"), "the admin's price"
    assert Decimal(str(hold.buffer)) == Decimal("3.20")

    errand = (await client.get(f"/errands/{resp.json()['id']}", headers=headers)).json()
    assert errand["items"][0]["name_snapshot"] == "Veg Puff", (
        "the admin's words, not the requester's"
    )


async def test_an_unknown_reference_is_refused(client, campus, make_user):
    """A stale or foreign id must not quietly degrade to an unpriced line -
    the requester would be shown one basket and charged for another."""
    requester_id, headers = await make_user("Requester")
    await _fund(requester_id, "1000")

    resp = await _shopping(
        client, headers,
        [{"name": "Ghost", "quantity": 1, "reference_id": str(uuid.uuid4())}],
    )
    assert resp.status_code == 422, resp.text


# ------------------------------------------------------------ fuzzy search


async def test_search_survives_a_typo(client, campus, make_user):
    admin_headers = await _admin(make_user)
    await _price(client, admin_headers, "Chicken Puff", 25, 15, 40)

    _, headers = await make_user("Requester")
    hits = (await client.get("/fraud/references/search?q=chikn+puf", headers=headers)).json()
    assert hits, "a dropped letter must not hide the item"
    assert hits[0]["display_name"] == "Chicken Puff"
    assert hits[0]["reference_price"] == 25.0


async def test_search_ignores_word_order_and_partials(client, campus, make_user):
    admin_headers = await _admin(make_user)
    await _price(client, admin_headers, "Cold Coffee", 40, 30, 60)

    _, headers = await make_user("Requester")
    for q in ("coffee cold", "cold cof", "cofee"):
        hits = (await client.get(f"/fraud/references/search?q={q}", headers=headers)).json()
        assert any(h["display_name"] == "Cold Coffee" for h in hits), q


async def test_search_offers_nothing_for_nonsense(client, campus, make_user):
    _, headers = await make_user("Requester")
    hits = (await client.get("/fraud/references/search?q=zzqqxx", headers=headers)).json()
    assert hits == [], "a box full of noise is worse than an empty one"


async def test_search_is_open_to_students(client, campus, make_user):
    """The rest of /references is admin-only, but a requester has to be able to
    find a priced item while building a list."""
    _, headers = await make_user("Requester")
    resp = await client.get("/fraud/references/search?q=tea", headers=headers)
    assert resp.status_code == 200
    assert (await client.get("/fraud/references", headers=headers)).status_code == 403
