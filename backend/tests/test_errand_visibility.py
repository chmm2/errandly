"""Who may read an errand.

Campus membership alone used to be the whole check, which meant any student
could fetch any errand on campus by id and read its requester, its assigned
runner, its progress, its items and its amounts — runs they had no part in, and
errands that finished months ago.

The rule is narrower: your own errands, plus work that is still open. An OPEN
errand is an offer to the campus and a runner deciding whether to take it has
to be able to read it. Once someone else accepts, it stops being an offer.
"""

import pytest

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def _post(client, headers, **over):
    body = {
        "category": "CUSTOM",
        "title": "Gate pickup",
        "pickup_label": "Main gate",
        "drop_lat": 12.9698,
        "drop_lng": 79.1559,
        "reward": 20,
        **over,
    }
    r = await client.post("/errands", json=body, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


async def test_open_work_is_readable_by_anyone_on_campus(client, campus, make_user):
    """A runner cannot decide whether to accept an errand they may not read."""
    _, requester = await make_user("Requester")
    _, stranger = await make_user("Stranger")
    errand = await _post(client, requester)
    r = await client.get(f"/errands/{errand['id']}", headers=stranger)
    assert r.status_code == 200


async def test_once_accepted_it_is_not_a_stranger_s_business(client, campus, make_user):
    """The leak this closes. Accepting makes it two people's errand, and its
    progress, amounts and parties stop being campus-readable."""
    _, requester = await make_user("Requester")
    _, runner = await make_user("Runner")
    _, stranger = await make_user("Stranger")

    errand = await _post(client, requester)
    accepted = await client.post(f"/errands/{errand['id']}/accept", headers=runner)
    assert accepted.status_code == 200, accepted.text

    r = await client.get(f"/errands/{errand['id']}", headers=stranger)
    assert r.status_code == 404, "a stranger should not even learn it exists"


async def test_both_parties_keep_access_after_acceptance(client, campus, make_user):
    _, requester = await make_user("Requester")
    _, runner = await make_user("Runner")
    errand = await _post(client, requester)
    await client.post(f"/errands/{errand['id']}/accept", headers=runner)

    assert (await client.get(f"/errands/{errand['id']}", headers=requester)).status_code == 200
    assert (await client.get(f"/errands/{errand['id']}", headers=runner)).status_code == 200
