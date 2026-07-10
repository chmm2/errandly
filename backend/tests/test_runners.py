import pytest

pytestmark = pytest.mark.asyncio(loop_scope="session")

# VIT Vellore-ish coordinates, a few hundred meters apart
NEAR = {"lat": 12.9692, "lng": 79.1559}
MID = {"lat": 12.9740, "lng": 79.1600}
FAR = {"lat": 12.9850, "lng": 79.1750}


def errand_payload(lat=NEAR["lat"], lng=NEAR["lng"], **overrides) -> dict:
    payload = {
        "category": "FOOD",
        "title": "Test feed errand",
        "pickup_label": "Canteen",
        "drop_lat": lat,
        "drop_lng": lng,
        "reward": 25,
    }
    payload.update(overrides)
    return payload


async def test_availability_toggle_requires_location(client, make_user):
    _, runner = await make_user("Runner")

    missing = await client.post(
        "/runners/me/availability", json={"is_available": True}, headers=runner
    )
    assert missing.status_code == 422  # no lat/lng

    on = await client.post(
        "/runners/me/availability",
        json={"is_available": True, **NEAR},
        headers=runner,
    )
    assert on.status_code == 200, on.text
    assert on.json()["is_available"] is True
    assert on.json()["active_load"] == 0

    off = await client.post(
        "/runners/me/availability", json={"is_available": False}, headers=runner
    )
    assert off.status_code == 200
    assert off.json()["is_available"] is False


async def test_feed_sorted_by_distance(client, make_user):
    _, requester = await make_user("Requester")
    _, runner = await make_user("Runner")

    near = (await client.post("/errands", json=errand_payload(**NEAR, title="near errand"),
                              headers=requester)).json()
    far = (await client.post("/errands", json=errand_payload(**FAR, title="far errand"),
                             headers=requester)).json()
    mid = (await client.post("/errands", json=errand_payload(**MID, title="mid errand"),
                             headers=requester)).json()

    resp = await client.get(
        "/errands", params={"lat": NEAR["lat"], "lng": NEAR["lng"], "limit": 50},
        headers=runner,
    )
    assert resp.status_code == 200, resp.text
    items = resp.json()["items"]
    ids = [e["id"] for e in items]
    assert ids.index(near["id"]) < ids.index(mid["id"]) < ids.index(far["id"])
    # distance annotated and monotonic for our three
    by_id = {e["id"]: e for e in items}
    assert by_id[near["id"]]["distance_m"] < by_id[mid["id"]]["distance_m"]
    assert by_id[mid["id"]]["distance_m"] < by_id[far["id"]]["distance_m"]


async def test_handoff_secret_gating_and_audit(client, make_user):
    _, requester = await make_user("Requester")
    _, runner = await make_user("Runner")
    _, stranger = await make_user("Stranger")

    errand = (
        await client.post(
            "/errands",
            json=errand_payload(
                category="CUSTOM",
                title="Collect my Swiggy order at the gate",
                external_ref="SWGY-123456",
                otp="4471",
                collect_amount=250,
            ),
            headers=requester,
        )
    ).json()
    eid = errand["id"]
    assert errand["fulfillment_type"] == "GATE_PICKUP"
    assert errand["has_handoff_secret"] is True

    # Nobody sees the OTP before accept — not even the would-be runner
    assert (await client.get(f"/errands/{eid}/handoff-secret", headers=runner)).status_code == 403

    await client.post(f"/errands/{eid}/accept", headers=runner)

    # Stranger still blocked after accept
    assert (
        await client.get(f"/errands/{eid}/handoff-secret", headers=stranger)
    ).status_code == 403

    # Assigned runner gets it
    secret = await client.get(f"/errands/{eid}/handoff-secret", headers=runner)
    assert secret.status_code == 200, secret.text
    body = secret.json()
    assert body["otp"] == "4471"
    assert body["external_ref"] == "SWGY-123456"
    assert body["collect_amount"] == 250

    # And the requester can see WHO viewed it in the audit trail
    events = (await client.get(f"/errands/{eid}/events", headers=requester)).json()
    assert "SECRET_VIEWED" in [e["event_type"] for e in events]

    # The OTP never leaks through errand serialization
    detail = (await client.get(f"/errands/{eid}", headers=stranger)).json()
    assert "4471" not in str(detail)


async def test_otp_rejected_for_catalog_categories(client, make_user):
    _, requester = await make_user("Requester")
    resp = await client.post(
        "/errands", json=errand_payload(category="FOOD", otp="1234"), headers=requester
    )
    assert resp.status_code == 422


async def test_load_cap_blocks_hoarding(client, make_user):
    _, requester = await make_user("Requester")
    _, runner = await make_user("Runner")

    first = (await client.post("/errands", json=errand_payload(title="run one"),
                               headers=requester)).json()
    second = (await client.post("/errands", json=errand_payload(title="run two"),
                                headers=requester)).json()
    third = (await client.post("/errands", json=errand_payload(title="run three"),
                               headers=requester)).json()

    assert (await client.post(f"/errands/{first['id']}/accept", headers=runner)).status_code == 200
    assert (
        await client.post(f"/errands/{second['id']}/accept", headers=runner)
    ).status_code == 200

    # Default max_load is 2 — the third accept must be refused
    blocked = await client.post(f"/errands/{third['id']}/accept", headers=runner)
    assert blocked.status_code == 409
    assert "active runs" in blocked.json()["detail"]

    # Delivering one frees a slot
    await client.post(f"/errands/{first['id']}/pickup", headers=runner)
    await client.post(f"/errands/{first['id']}/deliver", headers=runner)
    assert (await client.post(f"/errands/{third['id']}/accept", headers=runner)).status_code == 200


async def test_offer_event_recorded_for_available_runner(client, make_user):
    """Creating an errand offers it to nearby available runners (Redis GEO)."""
    _, requester = await make_user("Requester")
    _, runner = await make_user("Runner")

    on = await client.post(
        "/runners/me/availability", json={"is_available": True, **NEAR}, headers=runner
    )
    assert on.status_code == 200

    errand = (await client.post("/errands", json=errand_payload(title="offered errand"),
                                headers=requester)).json()

    events = (await client.get(f"/errands/{errand['id']}/events", headers=requester)).json()
    offered = [e for e in events if e["event_type"] == "OFFERED"]
    assert offered, events
    assert offered[0]["payload"]["runners"] >= 1
