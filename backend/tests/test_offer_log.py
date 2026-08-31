"""What the offer log has to record, and what it must never cost.

The table exists to answer one question that is currently unanswerable: how
much of a pair's shared history did the router cause? Matching boosts friends
up the offer queue, and ring detection reads "friends transacting with each
other" as evidence — so `circulation` partly measures the router rather than
the people. Separating them needs the policy's own expectation at offer time.

Two things therefore have to hold. The log must capture enough to recompute the
ranking counterfactually (every term, not just the final order), and it must be
incapable of costing an errand anything, because it is analytics sitting on a
dispatch path.
"""

import uuid

import pytest
from sqlalchemy import select

from app.core.database import SessionLocal
from app.core.redis import redis_client
from app.modules.errands.models import Errand, OfferLog
from app.modules.errands.service import (
    NEUTRAL_REPUTATION,
    SOCIAL_WEIGHT_M,
    _offer_to_nearby_runners,
    _terms_for,
)

async_test = pytest.mark.asyncio(loop_scope="session")

ERRAND_PAYLOAD = {
    "category": "FOOD",
    "title": "Maggi from DC canteen",
    "pickup_label": "Darling Canteen",
    "drop_lat": 12.9692,
    "drop_lng": 79.1559,
    "drop_label": "Block A, Room 402",
    "reward": 30,
}
AT_DROP = {"is_available": True, "lat": 12.9692, "lng": 79.1559}


async def _available(client, headers):
    resp = await client.post("/runners/me/availability", json=AT_DROP, headers=headers)
    assert resp.status_code == 200, resp.text


async def _logs_for(errand_id):
    async with SessionLocal() as db:
        rows = await db.scalars(
            select(OfferLog).where(OfferLog.errand_id == errand_id).order_by(OfferLog.round_no)
        )
        return list(rows)


# ------------------------------------------------------------------- terms


def test_the_log_and_the_ranking_share_one_formula():
    """The whole point of _terms_for. If the log recomputed the ranking rule
    separately the two would drift, and a counterfactual built on a stale copy
    of the rule is worse than having no counterfactual at all."""
    rid = uuid.uuid4()
    terms = _terms_for(rid, 500.0, {rid: {"trust": 1.0, "hops": 1}}, {rid: 4.5}, {rid: 0.0})
    assert terms["effective"] == pytest.approx(
        500.0 - 1.0 * SOCIAL_WEIGHT_M - (4.5 - NEUTRAL_REPUTATION) * 800.0
    )


def test_every_term_is_stored_not_just_the_verdict():
    """`effective` alone cannot be un-mixed back into its parts, so re-ranking
    with the social term zeroed — the counterfactual this table exists for —
    would be impossible from the score by itself."""
    rid = uuid.uuid4()
    terms = _terms_for(rid, 500.0, {rid: {"trust": 1.0, "hops": 2}}, {rid: 4.0}, {rid: 30.0})
    assert set(terms) == {
        "runner_id", "distance_m", "trust", "hops", "reputation", "penalty", "effective"
    }
    # The counterfactual is recomputable from what was kept.
    assert terms["effective"] - (-terms["trust"] * SOCIAL_WEIGHT_M) == pytest.approx(
        terms["distance_m"]
        - (terms["reputation"] - NEUTRAL_REPUTATION) * 800.0
        + terms["penalty"]
    )


def test_an_unknown_candidate_falls_back_to_neutral_rather_than_zero():
    """A runner the graph has never heard of is unknown, not untrusted. Scoring
    them at zero reputation would be a punishment nobody decided."""
    rid = uuid.uuid4()
    terms = _terms_for(rid, 100.0, None, None, None)
    assert terms["trust"] == 0.0
    assert terms["reputation"] == NEUTRAL_REPUTATION
    assert terms["hops"] is None
    assert terms["effective"] == pytest.approx(100.0)


# ------------------------------------------------------------------ wiring


@async_test
async def test_posting_an_errand_records_the_round_it_was_dispatched_in(client, make_user):
    """The wiring no unit test reaches: everything above would keep passing if
    dispatch never called the logger at all.

    Creating an errand dispatches it, so the round is logged without any test
    having to reach into the service.
    """
    requester_id, requester = await make_user("Requester")
    runner_id, runner = await make_user("Runner")
    await _available(client, runner)

    created = await client.post("/errands", json=ERRAND_PAYLOAD, headers=requester)
    assert created.status_code == 201, created.text
    errand_id = uuid.UUID(created.json()["id"])

    logs = await _logs_for(errand_id)
    assert len(logs) == 1
    row = logs[0]
    assert row.round_no == 1
    assert row.requester_id == requester_id
    ids = [c["runner_id"] for c in row.candidates]
    assert str(runner_id) in ids
    # Rank is stored explicitly rather than implied by list position, so a
    # later re-serialisation cannot silently reorder the evidence.
    assert [c["rank"] for c in row.candidates] == list(range(len(row.candidates)))


@async_test
async def test_each_dispatch_round_is_its_own_row(client, make_user):
    """A re-offer happens under a different candidate set and different scores.
    Collapsing rounds into one row would average away the very variation the
    estimate depends on."""
    _, requester = await make_user("Requester")
    _, runner = await make_user("Runner")
    await _available(client, runner)

    created = await client.post("/errands", json=ERRAND_PAYLOAD, headers=requester)
    errand_id = uuid.UUID(created.json()["id"])

    async with SessionLocal() as db:                      # a second round
        errand = await db.get(Errand, errand_id)
        await _offer_to_nearby_runners(db, redis_client, errand)
        await db.commit()

    assert [r.round_no for r in await _logs_for(errand_id)] == [1, 2]


@async_test
async def test_accepting_stamps_the_round_it_was_taken_from(client, make_user):
    """Without the outcome the candidate set is a question with no answer."""
    _, requester = await make_user("Requester")
    runner_id, runner = await make_user("Runner")
    await _available(client, runner)

    created = await client.post("/errands", json=ERRAND_PAYLOAD, headers=requester)
    errand_id = uuid.UUID(created.json()["id"])

    accepted = await client.post(f"/errands/{errand_id}/accept", headers=runner)
    assert accepted.status_code == 200, accepted.text

    logs = await _logs_for(errand_id)
    assert logs[-1].accepted_runner_id == runner_id
    assert logs[-1].accepted_at is not None


@async_test
async def test_a_round_nobody_took_is_recorded_as_such(client, make_user):
    """An unaccepted offer is data, not a gap: 'the policy suggested these
    people and none of them wanted it' is exactly as informative as a take."""
    _, requester = await make_user("Requester")
    _, runner = await make_user("Runner")
    await _available(client, runner)

    created = await client.post("/errands", json=ERRAND_PAYLOAD, headers=requester)
    errand_id = uuid.UUID(created.json()["id"])

    assert (await _logs_for(errand_id))[0].accepted_runner_id is None


# ----------------------------------------------------------------- safety


@async_test
async def test_a_logging_failure_never_costs_an_errand(client, make_user, monkeypatch):
    """The property that matters most. This sits on the dispatch path, and an
    analytics table must not be able to stop somebody's dinner arriving.

    The break is aimed at the model the logger instantiates rather than at
    _terms_for, which ranking also uses — sabotaging a shared helper would test
    that ranking fails safely, which is a different (and much stronger) claim
    than the one being made here.
    """
    _, requester = await make_user("Requester")
    _, runner = await make_user("Runner")
    await _available(client, runner)

    from app.modules.errands import service as errands_service

    def _explode(*_a, **_kw):
        raise RuntimeError("offer log is broken")

    monkeypatch.setattr(errands_service, "OfferLog", _explode)

    created = await client.post("/errands", json=ERRAND_PAYLOAD, headers=requester)
    assert created.status_code == 201, "dispatch must survive the logger failing"
    errand_id = uuid.UUID(created.json()["id"])

    assert await _logs_for(errand_id) == []

    # And the errand is genuinely usable, not merely created.
    accepted = await client.post(f"/errands/{errand_id}/accept", headers=runner)
    assert accepted.status_code == 200, accepted.text
