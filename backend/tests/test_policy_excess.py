"""Whether the routing policy already explains a group's in-group activity.

The collusion detector finds a closed money cycle among mutual friends. So does
an entirely honest friend group, because matching offers errands to friends
first — the harder the social boost, the more of it they circulate. These tests
pin the comparison that separates the two, and the two properties that keep it
from becoming a new way to accuse people.
"""

import uuid

import pytest

from app.modules.fraud import policy
from app.modules.fraud.policy import PolicyExcess, _acceptance_probabilities

# Session loop scope, matching the rest of the suite: a function-scoped
# loop here tears down the shared fixtures the other tests rely on.
pytestmark = pytest.mark.asyncio(loop_scope="session")


def _cand(rid, effective):
    return {"runner_id": str(rid), "effective": effective}


# ─────────────────────────────────────────────── turning scores into preference


async def test_the_best_scoring_candidate_is_the_most_likely_to_take_it():
    a, b = uuid.uuid4(), uuid.uuid4()
    probs = _acceptance_probabilities([_cand(a, -50.0), _cand(b, 900.0)])
    assert probs[0] > probs[1]
    assert sum(probs) == pytest.approx(1.0)


async def test_candidates_scoring_alike_are_equally_likely():
    """Offers go to everyone at once and the first to tap wins, so a small gap
    in score must not read as a near-certainty about who accepted."""
    a, b = uuid.uuid4(), uuid.uuid4()
    probs = _acceptance_probabilities([_cand(a, 100.0), _cand(b, 100.0)])
    assert probs[0] == pytest.approx(probs[1])


async def test_a_large_gap_becomes_a_strong_preference():
    a, b = uuid.uuid4(), uuid.uuid4()
    probs = _acceptance_probabilities([_cand(a, 0.0), _cand(b, 3000.0)])
    assert probs[0] > 0.99


# ───────────────────────────────────────────────────────── the verdict itself


def _excess(observed, expected, z, rounds=60, explored=3):
    return PolicyExcess(rounds=rounds, observed=observed, expected=expected,
                        z=z, explored_rounds=explored)


async def test_activity_the_policy_predicted_is_not_evidence():
    """The honest friend group. They transact constantly, but the router put
    them together every time, so there is nothing left to explain."""
    e = _excess(observed=57, expected=56.0, z=0.4)
    assert e.explained
    assert e.as_details()["explained_by_policy"] is True


async def test_activity_the_policy_cannot_explain_survives():
    """The ring. They chose each other far beyond what the router suggested."""
    e = _excess(observed=57, expected=20.0, z=7.9)
    assert not e.explained


async def test_the_threshold_is_a_test_statistic_not_a_tuned_constant():
    """The point of the whole exercise: 'how surprising is this?' now has a
    number attached, rather than a hand-picked share."""
    assert policy.Z_UNEXPLAINED >= 3.0
    assert _excess(50, 40.0, z=2.99).explained
    assert not _excess(50, 40.0, z=3.01).explained


async def test_the_details_an_admin_sees_carry_the_evidence():
    d = _excess(observed=57, expected=20.0, z=7.9, rounds=60, explored=4).as_details()
    assert d["observed_share"] == pytest.approx(0.95)
    assert d["expected_share"] == pytest.approx(0.333, abs=0.01)
    assert d["excess_share"] > 0.6
    assert d["explored_rounds"] == 4


# ──────────────────────────────────────────────────────────────── safety


async def test_a_group_of_one_is_not_a_group():
    assert await policy.excess_for_group(None, [uuid.uuid4()]) is None


class _EmptyDB:
    async def scalars(self, _stmt):
        return iter([])


async def test_too_little_history_returns_nothing_rather_than_a_guess():
    """The state every deployment starts in. Silence here must leave the
    detector behaving exactly as it did before — a fraud verdict that changes
    because an analytics table is thin would be worse than not consulting it."""
    assert await policy.excess_for_group(_EmptyDB(), [uuid.uuid4(), uuid.uuid4()]) is None


async def test_the_minimum_sample_is_large_enough_to_mean_something():
    """Three errands between two people cannot support a claim about what the
    policy expected."""
    assert policy.MIN_ROUNDS >= 20


async def test_the_window_matches_the_money_window():
    """Both halves of the evidence must describe the same period, or the
    comparison is between a cycle from one era and a policy from another."""
    from app.modules.fraud import collusion
    assert policy.WINDOW_DAYS == collusion.MONEY_WINDOW_DAYS
