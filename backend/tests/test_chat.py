import pytest

pytestmark = pytest.mark.asyncio(loop_scope="session")

NEAR = {"lat": 12.9692, "lng": 79.1559}


def errand_payload(**overrides) -> dict:
    payload = {
        "category": "FOOD",
        "title": "Chat test errand",
        "pickup_label": "Canteen",
        "drop_lat": NEAR["lat"],
        "drop_lng": NEAR["lng"],
        "reward": 25,
    }
    payload.update(overrides)
    return payload


async def test_chat_between_parties(client, make_user):
    _, requester = await make_user("Requester")
    _, runner = await make_user("Runner")
    _, stranger = await make_user("Stranger")

    errand = (await client.post("/errands", json=errand_payload(), headers=requester)).json()
    eid = errand["id"]

    # No chat before a runner is assigned
    early = await client.post(f"/errands/{eid}/chat", json={"body": "hi"}, headers=requester)
    assert early.status_code == 409

    await client.post(f"/errands/{eid}/accept", headers=runner)

    # Both parties can send
    m1 = await client.post(
        f"/errands/{eid}/chat", json={"body": "On my way to the canteen"}, headers=runner
    )
    assert m1.status_code == 201, m1.text
    assert m1.json()["sender_name"] == "Runner"
    m2 = await client.post(
        f"/errands/{eid}/chat", json={"body": "Thanks! extra ketchup please"}, headers=requester
    )
    assert m2.status_code == 201

    # History is ordered and shared
    history = (await client.get(f"/errands/{eid}/chat", headers=requester)).json()
    assert [m["body"] for m in history] == [
        "On my way to the canteen",
        "Thanks! extra ketchup please",
    ]
    # Runner sees the same thread
    runner_view = (await client.get(f"/errands/{eid}/chat", headers=runner)).json()
    assert len(runner_view) == 2

    # A stranger can neither read nor write
    assert (await client.get(f"/errands/{eid}/chat", headers=stranger)).status_code == 403
    assert (
        await client.post(f"/errands/{eid}/chat", json={"body": "sneaky"}, headers=stranger)
    ).status_code == 403
