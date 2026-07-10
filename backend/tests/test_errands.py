import asyncio

import pytest

pytestmark = pytest.mark.asyncio(loop_scope="session")

ERRAND_PAYLOAD = {
    "category": "FOOD",
    "title": "Maggi from DC canteen",
    "notes": "Extra ketchup please",
    "pickup_label": "Darling Canteen",
    "drop_lat": 12.9692,
    "drop_lng": 79.1559,
    "drop_label": "Block A, Room 402",
    "reward": 30,
}


async def _create(client, headers) -> dict:
    resp = await client.post("/errands", json=ERRAND_PAYLOAD, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()


async def test_create_and_feed(client, make_user):
    _, requester = await make_user("Requester")
    _, runner = await make_user("Runner")

    errand = await _create(client, requester)
    assert errand["status"] == "OPEN"
    assert errand["version"] == 1
    assert errand["runner_id"] is None

    # Own errands never appear in your feed
    own_feed = (await client.get("/errands", headers=requester)).json()
    assert errand["id"] not in [e["id"] for e in own_feed["items"]]

    # Other students on the campus see it
    feed = (await client.get("/errands", headers=runner)).json()
    assert errand["id"] in [e["id"] for e in feed["items"]]


async def test_full_lifecycle_with_audit(client, make_user):
    requester_id, requester = await make_user("Requester")
    runner_id, runner = await make_user("Runner")
    errand = await _create(client, requester)
    eid = errand["id"]

    accepted = await client.post(f"/errands/{eid}/accept", headers=runner)
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["status"] == "ACCEPTED"
    assert accepted.json()["runner_id"] == str(runner_id)
    assert accepted.json()["version"] == 2

    picked = await client.post(f"/errands/{eid}/pickup", headers=runner)
    assert picked.status_code == 200
    assert picked.json()["status"] == "IN_PROGRESS"

    delivered = await client.post(f"/errands/{eid}/deliver", headers=runner)
    assert delivered.status_code == 200
    assert delivered.json()["status"] == "DELIVERED"
    assert delivered.json()["delivered_at"] is not None

    # Only the requester confirms completion
    completed = await client.post(f"/errands/{eid}/complete", headers=requester)
    assert completed.status_code == 200
    assert completed.json()["status"] == "COMPLETED"
    assert completed.json()["version"] == 5

    # Event-sourced audit trail recorded every transition, in order
    events = (await client.get(f"/errands/{eid}/events", headers=requester)).json()
    assert [e["event_type"] for e in events] == [
        "CREATED", "ACCEPTED", "PICKED_UP", "DELIVERED", "COMPLETED",
    ]


async def test_illegal_transitions_rejected(client, make_user):
    _, requester = await make_user("Requester")
    _, runner = await make_user("Runner")
    errand = await _create(client, requester)
    eid = errand["id"]

    await client.post(f"/errands/{eid}/accept", headers=runner)

    # ACCEPTED -> DELIVERED skips IN_PROGRESS
    resp = await client.post(f"/errands/{eid}/deliver", headers=runner)
    assert resp.status_code == 409

    # ACCEPTED -> COMPLETED skips two states
    resp = await client.post(f"/errands/{eid}/complete", headers=requester)
    assert resp.status_code == 409

    # Double accept
    _, second_runner = await make_user("Second Runner")
    resp = await client.post(f"/errands/{eid}/accept", headers=second_runner)
    assert resp.status_code == 409


async def test_permission_guards(client, make_user):
    _, requester = await make_user("Requester")
    _, runner = await make_user("Runner")
    _, stranger = await make_user("Stranger")
    errand = await _create(client, requester)
    eid = errand["id"]

    # You cannot run your own errand
    resp = await client.post(f"/errands/{eid}/accept", headers=requester)
    assert resp.status_code == 403

    await client.post(f"/errands/{eid}/accept", headers=runner)

    # Only the assigned runner advances the errand
    resp = await client.post(f"/errands/{eid}/pickup", headers=stranger)
    assert resp.status_code == 403

    # Only the requester cancels
    resp = await client.post(f"/errands/{eid}/cancel", headers=runner)
    assert resp.status_code == 403


async def test_cancel_rules(client, make_user):
    _, requester = await make_user("Requester")
    _, runner = await make_user("Runner")

    # Cancel while OPEN is fine
    open_errand = await _create(client, requester)
    resp = await client.post(
        f"/errands/{open_errand['id']}/cancel",
        json={"reason": "Changed my mind"},
        headers=requester,
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "CANCELLED"

    # Cancel after ACCEPTED is fine (runner hasn't picked up)
    accepted_errand = await _create(client, requester)
    await client.post(f"/errands/{accepted_errand['id']}/accept", headers=runner)
    resp = await client.post(f"/errands/{accepted_errand['id']}/cancel", headers=requester)
    assert resp.status_code == 200

    # Cancel after pickup is NOT allowed — runner is already carrying it
    running_errand = await _create(client, requester)
    await client.post(f"/errands/{running_errand['id']}/accept", headers=runner)
    await client.post(f"/errands/{running_errand['id']}/pickup", headers=runner)
    resp = await client.post(f"/errands/{running_errand['id']}/cancel", headers=requester)
    assert resp.status_code == 409


async def test_concurrent_accept_exactly_one_wins(client, make_user):
    """The demo scenario: N runners race to accept one errand.

    Layer 1 (Redis SET NX) fast-fails most; layer 2 (SELECT FOR UPDATE +
    state machine) guarantees correctness. Exactly one accept succeeds."""
    _, requester = await make_user("Requester")
    runners = [await make_user(f"Racer {i}") for i in range(5)]
    errand = await _create(client, requester)
    eid = errand["id"]

    responses = await asyncio.gather(
        *[client.post(f"/errands/{eid}/accept", headers=h) for _, h in runners]
    )
    statuses = sorted(r.status_code for r in responses)
    assert statuses == [200, 409, 409, 409, 409], statuses

    # The winner recorded on the errand matches the single 200
    winner_resp = next(r for r in responses if r.status_code == 200)
    detail = (await client.get(f"/errands/{eid}", headers=requester)).json()
    assert detail["status"] == "ACCEPTED"
    assert detail["runner_id"] == winner_resp.json()["runner_id"]

    # Exactly one ACCEPTED event in the audit trail
    events = (await client.get(f"/errands/{eid}/events", headers=requester)).json()
    assert [e["event_type"] for e in events].count("ACCEPTED") == 1


async def test_create_rate_limited(client, make_user):
    _, requester = await make_user("Requester")

    for _ in range(10):
        resp = await client.post("/errands", json=ERRAND_PAYLOAD, headers=requester)
        assert resp.status_code == 201

    throttled = await client.post("/errands", json=ERRAND_PAYLOAD, headers=requester)
    assert throttled.status_code == 429
    assert "Retry-After" in throttled.headers


async def test_my_errands(client, make_user):
    _, requester = await make_user("Requester")
    _, runner = await make_user("Runner")
    errand = await _create(client, requester)
    await client.post(f"/errands/{errand['id']}/accept", headers=runner)

    mine_requester = (await client.get("/errands/mine", headers=requester)).json()
    assert errand["id"] in [e["id"] for e in mine_requester["requested"]]

    mine_runner = (await client.get("/errands/mine", headers=runner)).json()
    assert errand["id"] in [e["id"] for e in mine_runner["running"]]
