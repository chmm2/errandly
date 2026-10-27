"""What an unreviewed flag does, and — mostly — what it must not do.

The flags themselves are tested elsewhere. What is tested here is the sentence
they carry before any human has agreed with them, which is the part that can
quietly go wrong: a penalty curve that is too steep turns a suspicion nobody
checked into a ban nobody decided, and it does so invisibly, because the runner
it lands on simply stops being offered work and has nothing to appeal.

So most of these are tests that the punishment stays small.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.core.database import SessionLocal
from app.core.redis import redis_client
from app.modules.errands.models import Errand
from app.modules.errands.service import (
    NEUTRAL_REPUTATION,
    OFFER_CHANNEL_PREFIX,
    REPUTATION_WEIGHT_M,
    SOCIAL_WEIGHT_M,
    _offer_to_nearby_runners,
    _rank_with_scores,
)
from app.modules.fraud.integrity import (
    INTEGRITY_CAP_M,
    SEVERITY_WEIGHT_M,
    co_ringed_with,
    decay,
    penalties,
)
from app.modules.fraud.models import FraudFlag
from app.modules.fraud.service import PATTERN_WINDOW_DAYS

async_test = pytest.mark.asyncio(loop_scope="session")


# ------------------------------------------------------------------- fakes


class _FakeDB:
    """Enough AsyncSession to exercise both queries, including their failure.

    A stub rather than a real session on purpose: the interesting behaviour
    here is what happens when the database does NOT answer, and the reliable
    way to test that is to have it not answer.
    """

    def __init__(self, rows=(), details=(), boom=False):
        self._rows = list(rows)
        self._details = list(details)
        self._boom = boom

    async def execute(self, _stmt):
        if self._boom:
            raise RuntimeError("database unavailable")
        return iter(self._rows)

    async def scalars(self, _stmt):
        if self._boom:
            raise RuntimeError("database unavailable")
        return iter(self._details)


def _flag(user_id, severity, age_days=0.0):
    return (user_id, severity, datetime.now(UTC) - timedelta(days=age_days))


# -------------------------------------------------------------------- decay


def test_a_fresh_flag_counts_in_full():
    assert decay(0.0) == 1.0


def test_a_flag_nobody_reviewed_expires_with_the_strike_window():
    """Unreviewed evidence ages out on the same clock the strike ladder counts
    on, so a runner's standing and their ladder position never disagree about
    how old is old."""
    assert decay(PATTERN_WINDOW_DAYS) == 0.0
    assert decay(PATTERN_WINDOW_DAYS * 2) == 0.0


def test_decay_is_gradual_rather_than_a_cliff():
    assert decay(PATTERN_WINDOW_DAYS / 2) == pytest.approx(0.5)
    assert decay(1.0) > decay(10.0) > decay(25.0) > 0.0


# ------------------------------------------------------------ the sentence


def test_severity_orders_the_penalty():
    assert SEVERITY_WEIGHT_M[1] < SEVERITY_WEIGHT_M[2] < SEVERITY_WEIGHT_M[3]


def test_the_worst_single_flag_costs_less_than_one_friendship():
    """The whole design in one assertion. An open flag is a suspicion nobody
    has checked; it must not outweigh a fact the graph actually knows, or the
    detector starts overruling reality on its own authority."""
    assert SEVERITY_WEIGHT_M[3] < SOCIAL_WEIGHT_M


def test_a_flagged_runner_at_the_door_still_beats_a_clean_runner_far_away():
    """A demotion, not a removal. If the penalty could exceed any plausible
    campus distance it would be a ban wearing a ranking term's clothes."""
    flagged, clean = uuid.uuid4(), uuid.uuid4()
    nearby = [(flagged, 50.0), (clean, 2500.0)]

    ranked = _rank_with_scores(nearby, None, None, {flagged: INTEGRITY_CAP_M})
    assert ranked[0][0] == flagged


@async_test
async def test_flags_accumulate_but_never_past_the_cap():
    """Otherwise the demotion becomes a de-facto ban by accumulation — the hard
    filter this design rejected, arrived at without anyone deciding to."""
    runner = uuid.uuid4()
    db = _FakeDB(rows=[_flag(runner, 3) for _ in range(20)])

    result = await penalties(db, [runner])
    assert result[runner] == INTEGRITY_CAP_M


@async_test
async def test_two_flags_weigh_more_than_one():
    one, two = uuid.uuid4(), uuid.uuid4()
    db = _FakeDB(rows=[_flag(one, 1), _flag(two, 1), _flag(two, 1)])

    result = await penalties(db, [one, two])
    assert result[two] > result[one]


@async_test
async def test_an_old_flag_weighs_less_than_a_fresh_one():
    fresh, stale = uuid.uuid4(), uuid.uuid4()
    db = _FakeDB(rows=[_flag(fresh, 2, age_days=0), _flag(stale, 2, age_days=24)])

    result = await penalties(db, [fresh, stale])
    assert result[fresh] > result[stale] > 0.0


@async_test
async def test_an_unknown_severity_is_ignored_rather_than_guessed():
    """Severity is a 1-3 DB CHECK, so this needs a schema change to happen. If
    one lands, the safe reading of a band nobody has assigned a meaning to is
    zero, not an invented number."""
    runner = uuid.uuid4()
    db = _FakeDB(rows=[_flag(runner, 7)])

    assert await penalties(db, [runner]) == {}


# --------------------------------------------------------- absence is not guilt


@async_test
async def test_a_database_failure_penalises_nobody():
    """None, not {} — and the caller must then behave exactly as it did before
    this module existed. A hiccup must never be able to demote anyone."""
    assert await penalties(_FakeDB(boom=True), [uuid.uuid4()]) is None


@async_test
async def test_an_empty_candidate_set_is_answered_not_failed():
    assert await penalties(_FakeDB(), []) == {}


@async_test
async def test_nobody_flagged_is_a_fact_a_failed_lookup_is_not():
    """The `_safe_scores` distinction, kept: {} is an answer about people, None
    is the absence of one. Only the first may change what happens to anyone."""
    assert await penalties(_FakeDB(rows=[]), [uuid.uuid4()]) == {}


def test_ranking_is_untouched_when_no_penalties_are_known():
    a, b = uuid.uuid4(), uuid.uuid4()
    nearby = [(a, 100.0), (b, 200.0)]

    assert _rank_with_scores(nearby, None, None, None) == nearby
    assert _rank_with_scores(nearby, None, None, {}) == nearby


def test_a_penalty_only_ever_pushes_down_the_queue():
    """The one term in the formula that adds. An open flag must not be able to
    help anyone, however the arithmetic is fed."""
    a, b = uuid.uuid4(), uuid.uuid4()
    clean = _rank_with_scores([(a, 100.0), (b, 300.0)], None, None, None)
    flagged = _rank_with_scores([(a, 100.0), (b, 300.0)], None, None, {a: 400.0})

    assert clean[0][0] == a
    assert flagged[0][0] == b, "the penalty moved a, and it moved a backwards"


def test_the_penalty_is_commensurate_with_the_other_terms():
    """All four terms are metres, which is only true if they trade off. A
    severity-2 flag should be worth roughly a star of reputation."""
    flagged, clean = uuid.uuid4(), uuid.uuid4()
    nearby = [(flagged, 500.0), (clean, 500.0)]

    # Equal distance; the flagged runner is rated a full star higher.
    reps = {flagged: NEUTRAL_REPUTATION + 1.0, clean: NEUTRAL_REPUTATION}
    ranked = _rank_with_scores(nearby, None, reps, {flagged: SEVERITY_WEIGHT_M[2]})

    expected = flagged if REPUTATION_WEIGHT_M > SEVERITY_WEIGHT_M[2] else clean
    assert ranked[0][0] == expected


# --------------------------------------------------------------- the dyad


@async_test
async def test_ring_co_members_are_found_from_the_requesters_own_flag():
    """The sweep writes the whole membership onto every member's flag, so one
    indexed lookup on the requester yields everyone they were found circling
    money with."""
    requester, partner, stranger = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    db = _FakeDB(details=[{"members": [str(requester), str(partner)]}])

    assert await co_ringed_with(db, requester, [partner, stranger]) == {partner}


@async_test
async def test_only_candidates_actually_nearby_are_returned():
    requester, absent = uuid.uuid4(), uuid.uuid4()
    db = _FakeDB(details=[{"members": [str(requester), str(absent)]}])

    assert await co_ringed_with(db, requester, [uuid.uuid4()]) == set()


@async_test
async def test_the_requester_is_never_returned_as_their_own_co_member():
    requester = uuid.uuid4()
    db = _FakeDB(details=[{"members": [str(requester)]}])

    assert await co_ringed_with(db, requester, [requester]) == set()


@async_test
async def test_a_corrupt_member_id_does_not_discard_the_whole_finding():
    """details is free-form JSONB. One unparseable entry is a broken flag, not
    a reason to stop gating the members who did parse."""
    requester, partner = uuid.uuid4(), uuid.uuid4()
    db = _FakeDB(details=[{"members": [str(partner), "not-a-uuid", None]}])

    assert await co_ringed_with(db, requester, [partner]) == {partner}


@async_test
async def test_a_flag_with_no_members_excludes_nobody():
    requester, runner = uuid.uuid4(), uuid.uuid4()
    db = _FakeDB(details=[{"signature": "abc"}, None])

    assert await co_ringed_with(db, requester, [runner]) == set()


@async_test
async def test_a_failed_ring_lookup_excludes_nobody():
    """The failure that matters most: excluding people because the database
    stuttered would take runners off the platform for no reason at all."""
    assert await co_ringed_with(_FakeDB(boom=True), uuid.uuid4(), [uuid.uuid4()]) is None


@async_test
async def test_an_unflagged_requester_pairs_with_everyone():
    """The overwhelmingly common case, and the one a regression here would
    break silently for the entire campus."""
    assert await co_ringed_with(_FakeDB(details=[]), uuid.uuid4(), [uuid.uuid4()]) == set()


# ------------------------------------------------------------- upheld flags


@async_test
async def test_only_open_flags_are_weighed():
    """An UPHELD flag feeds the strike ladder, and the ladder already lowers
    reputation, which already lowers rank. Counting it here as well would
    punish one finding twice through two different mechanisms, and make the
    total impossible to explain to the person it lands on.

    Asserted against the query, because that is where the rule actually lives —
    a stub session cannot demonstrate a filter it never runs.
    """

    class _Capturing(_FakeDB):
        stmt = None

        async def execute(self, stmt):
            self.stmt = stmt
            return iter([])

    db = _Capturing()
    await penalties(db, [uuid.uuid4()])
    sql = str(db.stmt.compile(compile_kwargs={"literal_binds": True}))

    assert "'OPEN'" in sql
    assert "UPHELD" not in sql
    assert "DISMISSED" not in sql


# ------------------------------------------------------------------- wiring


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


class _RecordingRedis:
    """Real Redis, with the offer publishes noted down in order."""

    def __init__(self, inner):
        self._inner = inner
        self.published: list[str] = []

    def __getattr__(self, name):
        return getattr(self._inner, name)

    async def publish(self, channel, message):
        self.published.append(channel)
        return await self._inner.publish(channel, message)


async def _available(client, headers):
    resp = await client.post("/runners/me/availability", json=AT_DROP, headers=headers)
    assert resp.status_code == 200, resp.text


async def _open_flag(user_id, *, rule, severity, details=None):
    async with SessionLocal() as db:
        db.add(
            FraudFlag(
                user_id=user_id,
                rule=rule,
                severity=severity,
                status="OPEN",
                details=details,
            )
        )
        await db.commit()


@async_test
async def test_a_ring_partner_is_not_offered_this_requesters_errand(client, make_user):
    """The wiring, which no amount of unit testing reaches: every other test
    here calls the functions directly, and would keep passing if dispatch never
    called them at all."""
    requester_id, requester = await make_user("Requester")
    ringed_id, ringed = await make_user("Ring partner")
    clean_id, clean = await make_user("Unconnected runner")

    await _available(client, ringed)
    await _available(client, clean)

    created = await client.post("/errands", json=ERRAND_PAYLOAD, headers=requester)
    assert created.status_code == 201, created.text
    errand_id = uuid.UUID(created.json()["id"])

    await _open_flag(
        requester_id,
        rule="COLLUSION_RING",
        severity=3,
        details={"signature": "test", "members": [str(requester_id), str(ringed_id)]},
    )

    recorder = _RecordingRedis(redis_client)
    async with SessionLocal() as db:
        errand = await db.get(Errand, errand_id)
        await _offer_to_nearby_runners(db, recorder, errand)

    assert f"{OFFER_CHANNEL_PREFIX}{clean_id}" in recorder.published, (
        "an unrelated runner must still be offered the errand"
    )
    assert f"{OFFER_CHANNEL_PREFIX}{ringed_id}" not in recorder.published


@async_test
async def test_the_same_ring_partner_still_gets_everyone_elses_errands(client, make_user):
    """The limit of the refusal, and the reason it is defensible. The dyad is
    declined; the person is not. A flagged runner who was cut off from all work
    by a sweep would have been suspended without anyone deciding to."""
    requester_id, _ = await make_user("Requester")
    ringed_id, ringed = await make_user("Ring partner")
    _, bystander = await make_user("Unrelated requester")

    await _available(client, ringed)

    created = await client.post("/errands", json=ERRAND_PAYLOAD, headers=bystander)
    assert created.status_code == 201, created.text
    errand_id = uuid.UUID(created.json()["id"])

    await _open_flag(
        requester_id,
        rule="COLLUSION_RING",
        severity=3,
        details={"signature": "test", "members": [str(requester_id), str(ringed_id)]},
    )

    recorder = _RecordingRedis(redis_client)
    async with SessionLocal() as db:
        errand = await db.get(Errand, errand_id)
        await _offer_to_nearby_runners(db, recorder, errand)

    assert f"{OFFER_CHANNEL_PREFIX}{ringed_id}" in recorder.published


@async_test
async def test_an_open_flag_pushes_a_runner_down_the_real_offer_order(client, make_user):
    """Two runners standing in the same spot, so distance cannot break the tie
    and the penalty is the only thing left to order them."""
    _, requester = await make_user("Requester")
    flagged_id, flagged = await make_user("Flagged runner")
    clean_id, clean = await make_user("Clean runner")

    await _available(client, flagged)
    await _available(client, clean)

    created = await client.post("/errands", json=ERRAND_PAYLOAD, headers=requester)
    assert created.status_code == 201, created.text
    errand_id = uuid.UUID(created.json()["id"])

    await _open_flag(flagged_id, rule="RATING_FARMING", severity=3)

    recorder = _RecordingRedis(redis_client)
    async with SessionLocal() as db:
        errand = await db.get(Errand, errand_id)
        await _offer_to_nearby_runners(db, recorder, errand)

    order = recorder.published
    assert f"{OFFER_CHANNEL_PREFIX}{clean_id}" in order
    assert f"{OFFER_CHANNEL_PREFIX}{flagged_id}" in order, "demoted, never removed"
    assert order.index(f"{OFFER_CHANNEL_PREFIX}{clean_id}") < order.index(
        f"{OFFER_CHANNEL_PREFIX}{flagged_id}"
    )
