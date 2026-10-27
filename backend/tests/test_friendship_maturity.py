"""A friendship counts for less until it has been around a while.

The direction is the whole point, and it is the opposite of the obvious one. An
edge created yesterday is weak evidence — it could have been created for this
errand. An edge that has survived two years is strong. So trust ramps UP with
age rather than decaying, and nothing here penalises an old friendship.

This is the tie the farming work pushes attackers toward. Weighting ratings by
distinct rater made repetition worthless, so the cheapest evasion became
breadth: recruit many friends and have each rate once. Every one of those ties
has to be created, and created recently.
"""

import pytest

from app.modules.social.service import (
    FRIENDSHIP_MATURITY_DAYS,
    NEW_FRIENDSHIP_FLOOR,
    _maturity,
)


def test_a_friendship_made_today_counts_for_less():
    assert _maturity(0.0) == pytest.approx(NEW_FRIENDSHIP_FLOOR)


def test_it_reaches_full_weight_once_established():
    assert _maturity(FRIENDSHIP_MATURITY_DAYS) == pytest.approx(1.0)
    assert _maturity(FRIENDSHIP_MATURITY_DAYS * 10) == pytest.approx(1.0)


def test_age_never_reduces_trust():
    """The mistake this avoids. Decaying old edges would penalise long
    friendships, which are stronger evidence than new ones, and would punish
    the ordinary population to inconvenience nobody — rebuilding a stale
    network costs an attacker nothing."""
    ages = [0, 1, 7, 30, 90, 365, 3650]
    weights = [_maturity(float(a)) for a in ages]
    assert weights == sorted(weights), "maturity must be monotonically rising"
    assert weights[-1] == pytest.approx(1.0)


def test_a_new_friendship_is_discounted_not_erased():
    """Most new friendships are exactly what they look like. Zeroing them would
    make the app useless to anyone who joined this week."""
    assert 0 < NEW_FRIENDSHIP_FLOOR < 1
    assert _maturity(1.0) > NEW_FRIENDSHIP_FLOOR


def test_an_unknown_age_counts_in_full():
    """Edges written before `since` was recorded are genuinely old. Treating
    missing data as suspicious would penalise the platform's earliest users for
    the platform's own gap."""
    assert _maturity(None) == pytest.approx(1.0)


def test_recruiting_a_network_today_does_not_pay_off_today():
    """Eighty friends made this morning carry well under half the trust of
    eighty made last term, which is the cost the breadth evasion now has."""
    fresh = _maturity(0.0)
    established = _maturity(365.0)
    assert fresh < established / 2
