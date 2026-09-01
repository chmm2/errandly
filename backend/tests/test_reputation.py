"""Rating provenance: weighting, farming detection, and its effect on matching.

The weighting maths is pure and tested directly. The case to watch throughout
is not the farmer — it is the runner whose friends genuinely like them, who
must come through all of this untouched.
"""

import uuid

import pytest

from app.modules.errands.service import (
    NEUTRAL_REPUTATION,
    REPUTATION_WEIGHT_M,
    SOCIAL_WEIGHT_M,
    _rank_with_scores,
)
from app.modules.fraud import reputation
from app.modules.fraud.reputation import RatingProfile, farming_signals, rating_weight

async_test = pytest.mark.asyncio(loop_scope="session")


# ------------------------------------------------------------------ weighting


def test_a_strangers_rating_always_counts_in_full():
    """Independent evidence is never discounted, whatever the runner's mix."""
    assert rating_weight(concentration=0.0, rater_is_friend=False) == 1.0
    assert rating_weight(concentration=1.0, rater_is_friend=False) == 1.0


def test_friend_ratings_are_untouched_below_the_knee():
    """The case that must not break. Most runners have friends among their
    customers, and a platform that discounted every friend's rating would
    punish the honest majority to inconvenience a few."""
    assert rating_weight(concentration=0.2, rater_is_friend=True) == 1.0
    assert rating_weight(concentration=reputation.CONCENTRATION_KNEE, rater_is_friend=True) == 1.0


def test_the_discount_tracks_concentration_not_friendship():
    """A friend's rating is discounted only in proportion to how much of the
    runner's reputation rests on their own circle."""
    mild = rating_weight(concentration=0.7, rater_is_friend=True)
    heavy = rating_weight(concentration=1.0, rater_is_friend=True)
    assert 1.0 > mild > heavy
    assert heavy == pytest.approx(1.0 - reputation.MAX_RATING_DISCOUNT)


def test_a_rating_is_never_erased_entirely():
    """A real errand was really delivered. Zeroing the rating would punish the
    runner for who their customers happened to be."""
    assert rating_weight(concentration=1.0, rater_is_friend=True) > 0.0


# --------------------------------------------------------------- confidence


def test_a_runner_carried_by_their_circle_reads_as_unproven_not_bad():
    """The key move. Their score is not dragged down — it is pulled toward the
    middle, because there is little independent evidence either way."""
    farmed = RatingProfile(
        in_cluster=10, out_cluster=0, mean_in=5.0, weighted_score=5.0, weight_total=2.5
    )
    assert farmed.matching_score < 5.0
    assert farmed.matching_score > NEUTRAL_REPUTATION, "not punished, just unproven"
    assert farmed.confidence < 0.3


def test_a_broadly_rated_runner_keeps_their_score():
    proven = RatingProfile(
        in_cluster=5, out_cluster=25, mean_in=4.8, mean_out=4.7,
        weighted_score=4.75, weight_total=30.0,
    )
    assert proven.matching_score == pytest.approx(4.75, abs=0.3)
    assert proven.confidence > 0.75


# ----------------------------------------------------------------- farming


def test_a_well_liked_runner_with_friendly_customers_is_not_flagged():
    """The false positive that would matter most. Concentrated, highly rated,
    and entirely honest — friends rate them the same as strangers do."""
    assert farming_signals(RatingProfile(
        in_cluster=8, out_cluster=6, mean_in=4.8, mean_out=4.7,
        weighted_score=4.75, weight_total=13.0,
    )) is None


def test_a_gap_between_friends_and_strangers_is_flagged():
    """Friends say five, strangers say two. One of them is not describing the
    same runner."""
    signals = farming_signals(RatingProfile(
        in_cluster=9, out_cluster=3, mean_in=5.0, mean_out=2.2,
        weighted_score=4.3, weight_total=9.0,
    ))
    assert signals is not None
    assert signals["differential"] == pytest.approx(2.8)
    assert any("higher than strangers" in r for r in signals["reasons"])


def test_praise_arriving_right_after_a_penalty_is_flagged_on_its_own():
    """The timing route, which needs no strangers at all — and the runner who
    has stopped getting stranger work is exactly the one farming."""
    signals = farming_signals(RatingProfile(
        in_cluster=6, out_cluster=0, mean_in=5.0,
        post_penalty_in_cluster=4, weighted_score=5.0, weight_total=1.5,
    ))
    assert signals is not None
    assert signals["post_penalty_burst"] == 4
    assert any("within" in r for r in signals["reasons"])


def test_a_few_friendly_ratings_are_never_a_pattern():
    """Below the floor there is nothing to conclude, however lopsided it looks."""
    assert farming_signals(RatingProfile(
        in_cluster=2, out_cluster=0, mean_in=5.0, weighted_score=5.0, weight_total=2.0
    )) is None


def test_a_high_score_from_strangers_is_not_farming():
    """Low concentration exits before anything else is considered."""
    assert farming_signals(RatingProfile(
        in_cluster=2, out_cluster=30, mean_in=5.0, mean_out=4.9,
        weighted_score=4.9, weight_total=32.0,
    )) is None


# ------------------------------------------------------------------ ranking


def test_reputation_moves_a_runner_up_the_queue():
    """The link that was missing: a penalty must actually cost work. Before
    this, a flagged runner lost a star and was offered exactly as much."""
    good, bad = uuid.uuid4(), uuid.uuid4()
    # bad is nearer, good is 500m further away but rated a full star higher.
    nearby = [(bad, 100.0), (good, 600.0)]
    reps = {good: 4.5, bad: 3.5}

    ranked = _rank_with_scores(nearby, None, reps)
    assert ranked[0][0] == good, "a full star should outweigh 500m"


def test_distance_still_wins_when_reputation_is_close():
    a, b = uuid.uuid4(), uuid.uuid4()
    nearby = [(a, 100.0), (b, 900.0)]
    ranked = _rank_with_scores(nearby, None, {a: 3.6, b: 3.8})
    assert ranked[0][0] == a


def test_trust_and_reputation_both_count():
    """All three terms are in metres of effective distance, so their relative
    influence is legible rather than buried in incomparable scales."""
    friend_poor, stranger_good = uuid.uuid4(), uuid.uuid4()
    nearby = [(friend_poor, 500.0), (stranger_good, 500.0)]

    # Equal distance: a direct friend rated neutrally vs a stranger rated well.
    scores = {friend_poor: {"trust": 1.0}}
    reps = {friend_poor: NEUTRAL_REPUTATION, stranger_good: 5.0}
    ranked = _rank_with_scores(nearby, scores, reps)

    friend_bonus = SOCIAL_WEIGHT_M
    rep_bonus = (5.0 - NEUTRAL_REPUTATION) * REPUTATION_WEIGHT_M
    expected = friend_poor if friend_bonus > rep_bonus else stranger_good
    assert ranked[0][0] == expected


def test_ranking_is_unchanged_when_nothing_is_known():
    a, b = uuid.uuid4(), uuid.uuid4()
    nearby = [(a, 100.0), (b, 200.0)]
    assert _rank_with_scores(nearby, None, None) == nearby


# ------------------------------------------------- one rater, one vote


def _farmed(ratings: int, friends: int) -> RatingProfile:
    """A profile built the way build_profile builds one: a single vote per
    person, carrying their own mean."""
    conc = 1.0
    w = rating_weight(conc, True)
    return RatingProfile(
        in_cluster=ratings,
        out_cluster=0,
        in_raters=friends,
        out_raters=0,
        mean_in=5.0,
        weighted_score=5.0,
        weight_total=w * friends,
    )


def _honest(strangers: int) -> RatingProfile:
    return RatingProfile(
        in_cluster=0,
        out_cluster=strangers,
        in_raters=0,
        out_raters=strangers,
        mean_out=5.0,
        weighted_score=5.0,
        weight_total=float(strangers),
    )


def test_patience_no_longer_beats_independence():
    """The exploit this closes.

    The discount bottoms out at 0.75, so a friend rating still carried 0.25 and
    weight grew without bound — roughly a hundred farmed ratings used to
    overtake twenty honest ones (4.64 against 4.57). Counting people instead of
    ratings removes the exploit rather than tuning the cap.
    """
    assert _farmed(100, 8).matching_score < _honest(20).matching_score
    assert _farmed(1000, 8).matching_score < _honest(20).matching_score


def test_a_farmed_score_saturates():
    """Adding ratings from the same circle stops buying anything at all."""
    assert _farmed(100, 8).matching_score == pytest.approx(
        _farmed(300, 8).matching_score
    )


def test_an_honest_frequent_customer_costs_the_runner_nothing_real():
    """Twenty ratings from one person genuinely is one person's opinion, so
    capping it is not a penalty — it is the correct reading."""
    assert _farmed(20, 1).matching_score == pytest.approx(_farmed(5, 1).matching_score)


# --------------------------------------- the farmer nobody has penalised yet


def test_a_reputation_no_stranger_has_tested_is_flagged():
    """The gap the first two routes cannot see.

    The differential needs strangers to compare against and the burst needs a
    prior penalty, so a runner who farms from a standing start — never caught,
    never served a stranger — tripped neither.
    """
    farmer = RatingProfile(
        in_cluster=18, out_cluster=0, in_raters=5, out_raters=0,
        mean_in=5.0, weighted_score=5.0, weight_total=1.25,
    )
    signals = farming_signals(farmer)
    assert signals is not None
    assert any("no stranger has ever tested" in r for r in signals["reasons"])


def test_a_new_runner_whose_first_customers_were_friends_is_not_flagged():
    """The case that must survive all of this. Everyone starts here."""
    newcomer = RatingProfile(
        in_cluster=4, out_cluster=0, in_raters=4, out_raters=0,
        mean_in=5.0, weighted_score=5.0, weight_total=1.0,
    )
    assert farming_signals(newcomer) is None


def test_many_distinct_friends_is_a_customer_base_not_a_circle():
    """Eighteen ratings from fifteen different friends is a popular runner.
    The signal is repeat concentration, never friendship itself."""
    popular = RatingProfile(
        in_cluster=18, out_cluster=0, in_raters=15, out_raters=0,
        mean_in=4.8, weighted_score=4.8, weight_total=3.75,
    )
    assert farming_signals(popular) is None
