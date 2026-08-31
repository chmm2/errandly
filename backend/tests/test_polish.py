import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, update

from app.core.database import SessionLocal
from app.modules.auth.models import User
from app.modules.errands.models import Errand
from app.modules.notifications.models import Notification

pytestmark = pytest.mark.asyncio(loop_scope="session")

NEAR = {"lat": 12.9692, "lng": 79.1559}


def errand_payload(**overrides) -> dict:
    payload = {
        "category": "FOOD",
        "title": "Polish test errand",
        "pickup_label": "Canteen",
        "drop_lat": NEAR["lat"],
        "drop_lng": NEAR["lng"],
        "reward": 25,
    }
    payload.update(overrides)
    return payload


# ------------------------------------------------- runner profile disclosure

async def test_runner_summary_gated_to_parties_and_active_run(client, make_user):
    _, requester = await make_user("Requester")
    runner_id, runner = await make_user("Runner")
    _, stranger = await make_user("Stranger")

    async with SessionLocal() as db:
        await db.execute(
            update(User).where(User.id == runner_id).values(phone="9998887777")
        )
        await db.commit()

    errand = (await client.post("/errands", json=errand_payload(), headers=requester)).json()
    eid = errand["id"]

    # No runner yet
    assert (await client.get(f"/errands/{eid}", headers=requester)).json()["runner"] is None

    await client.post(f"/errands/{eid}/accept", headers=runner)

    # Requester sees the runner card WITH phone during the active run
    detail = (await client.get(f"/errands/{eid}", headers=requester)).json()
    assert detail["runner"]["display_name"] == "Runner"
    assert detail["runner"]["phone"] == "9998887777"
    assert detail["runner"]["reputation_score"] == 5.0

    # A bystander never sees the runner block — and since the errand has been
    # accepted, they no longer see the errand at all. Stripping the field was
    # the old, weaker version of this: it still confirmed the errand existed
    # and leaked its progress, items and amounts.
    assert (await client.get(f"/errands/{eid}", headers=stranger)).status_code == 404

    # After completion the name stays but the phone is withheld again
    await client.post(f"/errands/{eid}/pickup", headers=runner)
    await client.post(f"/errands/{eid}/deliver", headers=runner)
    await client.post(f"/errands/{eid}/complete", headers=requester)
    done = (await client.get(f"/errands/{eid}", headers=requester)).json()
    assert done["runner"]["display_name"] == "Runner"
    assert done["runner"]["phone"] is None


async def test_runner_card_shows_photo_and_delivery_count(client, make_user):
    _, requester = await make_user("Requester")
    runner_id, runner = await make_user("Runner")

    # runner sets a profile photo
    photo = "data:image/png;base64,iVBORw0KGgoAAAANS"
    resp = await client.put("/auth/me/photo", json={"photo_url": photo}, headers=runner)
    assert resp.status_code == 200
    assert resp.json()["photo_url"] == photo

    # complete one delivery so the count is > 0
    e1 = (await client.post("/errands", json=errand_payload(), headers=requester)).json()
    for step in ("accept", "pickup", "deliver"):
        await client.post(f"/errands/{e1['id']}/{step}", headers=runner)
    await client.post(f"/errands/{e1['id']}/complete", headers=requester)

    # a second, active errand: the requester sees the runner's photo + tally
    e2 = (await client.post("/errands", json=errand_payload(), headers=requester)).json()
    await client.post(f"/errands/{e2['id']}/accept", headers=runner)
    card = (await client.get(f"/errands/{e2['id']}", headers=requester)).json()["runner"]
    assert card["photo_url"] == photo
    assert card["trips_completed"] == 1


# ----------------------------------------------------- 10-minute expiry sweep

async def test_stale_open_errand_expires_and_notifies(client, make_user):
    from app.workers.consumers import expire_stale_open_errands

    requester_id, requester = await make_user("Requester")
    errand = (await client.post("/errands", json=errand_payload(), headers=requester)).json()
    eid = uuid.UUID(errand["id"])

    # Move the poster's deadline into the past instead of waiting for it.
    async with SessionLocal() as db:
        await db.execute(
            update(Errand)
            .where(Errand.id == eid)
            .values(expires_at=datetime.now(UTC) - timedelta(minutes=1))
        )
        await db.commit()

    await expire_stale_open_errands()

    detail = (await client.get(f"/errands/{eid}", headers=requester)).json()
    assert detail["status"] == "EXPIRED"

    async with SessionLocal() as db:
        note = await db.scalar(
            select(Notification).where(
                Notification.user_id == requester_id,
                Notification.type == "ERRAND_EXPIRED",
            )
        )
    assert note is not None


async def test_accepted_errand_is_not_expired(client, make_user):
    """The sweep must never touch an errand a runner already took."""
    from app.workers.consumers import expire_stale_open_errands

    _, requester = await make_user("Requester")
    _, runner = await make_user("Runner")
    errand = (await client.post("/errands", json=errand_payload(), headers=requester)).json()
    eid = uuid.UUID(errand["id"])
    await client.post(f"/errands/{eid}/accept", headers=runner)

    async with SessionLocal() as db:
        await db.execute(
            update(Errand)
            .where(Errand.id == eid)
            .values(created_at=datetime.now(UTC) - timedelta(minutes=20))
        )
        await db.commit()

    await expire_stale_open_errands()

    detail = (await client.get(f"/errands/{eid}", headers=requester)).json()
    assert detail["status"] == "ACCEPTED"  # untouched
