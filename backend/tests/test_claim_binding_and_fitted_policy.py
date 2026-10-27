"""Two fixes from the paper review.

1. A claim on an itemised order must name one of its lines, and a line the
   requester picked from the admin price list is judged against that reference
   whatever the runner calls it. Before, renaming a priced item until it
   matched nothing made it NO_REFERENCE, which is paid unchecked. Nor may a
   claim report more of a line than the requester ordered.
2. The policy test can use an acceptance model fitted to logged acceptances
   instead of the router's own scores.
"""

import uuid
from types import SimpleNamespace

import pytest

from app.modules.fraud import policy
from tests.test_price_report_gate import _admin, _fund, _price, _shopping_run

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def _setup(client, make_user):
    admin_headers = await _admin(make_user)
    ref = await _price(client, admin_headers, "Chicken Puff", 20, 15, 30)
    requester_id, r_headers = await make_user("Requester")
    _, run_headers = await make_user("Runner")
    await _fund(requester_id, "1000")
    errand = await _shopping_run(
        client, r_headers, run_headers,
        [{"name": "Chicken Puff", "quantity": 1, "reference_id": ref["id"]}],
    )
    return errand, run_headers


async def test_a_name_not_on_the_order_is_refused(client, campus, make_user):
    errand, run_headers = await _setup(client, make_user)
    resp = await client.post(
        f"/fraud/errands/{errand['id']}/claims",
        json={"lines": [{"name": "zzq special item", "unit_price": 60, "quantity": 1}]},
        headers=run_headers,
    )
    assert resp.status_code == 422, resp.text


async def test_a_renamed_priced_line_is_still_judged_against_its_reference(
    client, campus, make_user
):
    errand, run_headers = await _setup(client, make_user)
    resp = await client.post(
        f"/fraud/errands/{errand['id']}/claims",
        json={"lines": [{"name": "chiken puff", "unit_price": 60, "quantity": 1}]},
        headers=run_headers,
    )
    assert resp.status_code == 200, resp.text
    claim = resp.json()["claims"][0]
    assert claim["verdict"] == "FLAGGED"
    # Judged as the priced line it is (the snapshot may sit above 20 once the
    # shared test database has store history for this canteen).
    assert claim["item_key"] == "chicken puff"
    assert claim["reference_snapshot"] is not None


async def test_claiming_more_than_was_ordered_is_refused(client, campus, make_user):
    errand, run_headers = await _setup(client, make_user)
    resp = await client.post(
        f"/fraud/errands/{errand['id']}/claims",
        json={"lines": [{"name": "Chicken Puff", "unit_price": 20, "quantity": 3}]},
        headers=run_headers,
    )
    assert resp.status_code == 422, resp.text


# ------------------------------------------------------------ fitted model


def _round(candidates, taker):
    return SimpleNamespace(
        accepted_runner_id=uuid.UUID(taker) if taker else None,
        candidates=candidates,
    )


def _cand(rid, dist, hops=None):
    return {"runner_id": rid, "distance_m": dist, "hops": hops, "reputation": 3.5}


async def test_too_little_history_gives_no_model():
    a, b = str(uuid.uuid4()), str(uuid.uuid4())
    rows = [_round([_cand(a, 100), _cand(b, 900)], a) for _ in range(10)]
    assert policy.fit_acceptance_model(rows) is None


async def test_the_fitted_model_learns_that_nearer_runners_accept():
    rows = []
    for i in range(300):
        near, far = str(uuid.uuid4()), str(uuid.uuid4())
        # The nearer runner takes it three times in four.
        taker = near if i % 4 else far
        rows.append(_round([_cand(near, 100), _cand(far, 1100)], taker))
    model = policy.fit_acceptance_model(rows)
    assert model is not None
    assert model.coef[0] < 0, "distance must count against acceptance"
    p = model.probabilities([_cand("x", 100), _cand("y", 1100)])
    assert p[0] == pytest.approx(0.75, abs=0.05)
    assert sum(p) == pytest.approx(1.0)


class _Rows:
    def __init__(self, rows):
        self._rows = rows

    async def scalars(self, _stmt):
        return iter(self._rows)


async def test_beating_a_foregone_conclusion_is_not_explained():
    """When every round gave the group no chance at all, the variance is zero.
    Taking those rounds anyway used to read as z = 0, i.e. explained."""
    a, b = uuid.uuid4(), uuid.uuid4()
    rows = []
    for _ in range(30):
        stranger = str(uuid.uuid4())
        row = SimpleNamespace(
            requester_id=a, accepted_runner_id=b, exploring=False,
            candidates=[{"runner_id": str(b), "effective": 20000.0},
                        {"runner_id": stranger, "effective": 0.0}],
        )
        rows.append(row)
    ex = await policy.excess_for_group(_Rows(rows), [a, b])
    assert ex is not None
    assert not ex.explained
    assert ex.z == policy.Z_DEGENERATE


async def test_a_friend_who_always_accepts_is_not_explained_by_a_fitted_model():
    """The coordinated ring: the partner is the router's first pick every
    time. The router's own scores call that expected; a model fitted on how
    ordinary friends behave does not."""
    calib = []
    for i in range(400):
        friend, stranger = str(uuid.uuid4()), str(uuid.uuid4())
        calib.append(_round(
            [_cand(friend, 120, hops=1), _cand(stranger, 300)],
            friend if i % 2 else stranger,  # ordinary friends: half the time
        ))
    model = policy.fit_acceptance_model(calib)
    p = model.probabilities([_cand("f", 120, hops=1), _cand("s", 300)])
    assert 0.35 < p[0] < 0.65
