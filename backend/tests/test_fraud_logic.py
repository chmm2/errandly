"""Pure-logic tests for normalization and the reference estimator.

No database, no Redis, no event loop - these exercise the two pieces where a
subtle bug would be invisible in an integration test but would quietly decide
whether real people get suspended. They are the tests worth reading first.
"""

from decimal import Decimal

import pytest

from app.modules.fraud.estimator import (
    MIN_DISTINCT_RUNNERS,
    estimate_reference,
    propose_band,
)
from app.modules.fraud.normalize import normalize, resolve_key


def D(v) -> Decimal:
    return Decimal(str(v))


# ------------------------------------------------------------- normalization


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Chicken Puffs", "chicken puff"),
        ("chicken puff", "chicken puff"),
        ("CHKN PUF", "chicken puff"),
        ("  chicken   puffs  ", "chicken puff"),
        ("Chicken-Puff!", "chicken puff"),
        ("chiken puffs", "chicken puff"),
        ("Veg Puff", "vegetable puff"),
        ("café latte", "cafe latte"),
        ("2 Samosas", "2 samosa"),
    ],
)
def test_spellings_collapse_to_one_key(raw, expected):
    assert normalize(raw) == expected


def test_size_words_survive_normalization():
    """A large tea legitimately costs more than a small one. Collapsing them
    would hide a real price difference behind a fake match - and then flag
    an honest runner for buying the large."""
    assert normalize("Large Tea") != normalize("Small Tea")
    assert "large" in normalize("Large Tea")


def test_distinct_items_do_not_collapse():
    assert normalize("chicken puff") != normalize("chicken roll")
    assert normalize("veg puff") != normalize("chicken puff")


def test_fuzzy_match_finds_typo_against_known_keys():
    known = ["chicken puff", "vegetable puff", "masala tea"]
    key, matched = resolve_key("chicken pufff", known)
    assert (key, matched) == ("chicken puff", True)


def test_fuzzy_match_refuses_a_genuinely_different_item():
    known = ["chicken puff"]
    key, matched = resolve_key("mutton biryani", known)
    assert matched is False
    assert key == "mutton biryani"


def test_unknown_item_becomes_its_own_key():
    key, matched = resolve_key("Cold Coffee", [])
    assert key == "cold coffee"
    assert matched is False


def test_empty_name_yields_empty_key():
    assert resolve_key("   ", ["chicken puff"]) == ("", False)


# ---------------------------------------------------------------- estimator


def test_refuses_to_estimate_from_too_few_runners():
    """One chatty runner is not a market. Without independent corroboration
    the estimator must decline rather than guess."""
    est = estimate_reference({"runner-a": [D(20)] * 50})
    assert not est.usable
    assert est.distinct_runners == 1
    assert "insufficient evidence" in est.reason


def test_estimates_from_an_honest_spread():
    est = estimate_reference(
        {"a": [D(20), D(20)], "b": [D(21)], "c": [D(20)], "d": [D(19)]}
    )
    assert est.usable
    assert est.value == D("20.00")


def test_one_fraudster_cannot_move_the_reference_by_volume():
    """The defence that does the real work.

    A runner claiming 40 for a 20-rupee puff two hundred times collapses to a
    single 40 in the outer median. Honest runners outvote them, and the
    reference does not budge - so the fraud never becomes the new normal.
    """
    honest = {f"honest-{i}": [D(20)] for i in range(5)}
    fraudster = {"cheat": [D(40)] * 200}

    est = estimate_reference({**honest, **fraudster})

    assert est.usable
    assert est.value == D("20.00"), "volume must not buy influence over the reference"


def test_a_real_price_rise_still_moves_the_estimate():
    """The flip side: when everyone agrees the price went up, it must move.
    A detector that can never update is one that eventually flags everybody."""
    claims = {f"runner-{i}": [D(25)] for i in range(6)}
    est = estimate_reference(claims, band_min=D(15), band_max=D(30))
    assert est.usable
    assert est.value == D("25.00")


def test_estimate_outside_the_band_is_refused_and_proposed():
    """The circuit breaker. Even unanimous claims cannot push the reference
    outside admin-approved bounds - they can only ask a human to move them."""
    claims = {f"runner-{i}": [D(60)] for i in range(6)}
    est = estimate_reference(claims, band_min=D(15), band_max=D(30))

    assert not est.usable, "an out-of-band estimate must never apply itself"
    assert est.needs_proposal
    assert est.observed_median == D("60.00")
    assert "outside the approved band" in est.reason


def test_estimate_near_a_band_edge_applies_but_still_asks():
    claims = {f"runner-{i}": [D("29.50")] for i in range(6)}
    est = estimate_reference(claims, band_min=D(15), band_max=D(30))
    assert est.usable
    assert est.needs_proposal
    assert "near a band edge" in est.reason


def test_outliers_are_dropped_before_the_estimate():
    claims = {f"runner-{i}": [D(20)] for i in range(6)}
    claims["wild"] = [D(500)]
    est = estimate_reference(claims)
    assert est.value == D("20.00")
    assert est.outliers_dropped >= 1


def test_minimum_runner_threshold_is_actually_enforced():
    claims = {f"runner-{i}": [D(20), D(20)] for i in range(MIN_DISTINCT_RUNNERS - 1)}
    assert not estimate_reference(claims).usable


def test_proposed_band_brackets_the_observation():
    lo, hi = propose_band(D(25))
    assert lo < D(25) < hi
    assert lo > 0


def test_an_approved_alias_resolves_a_name_spelling_cannot_reach():
    """The gap tiers 1 and 2 leave. "patties" and "puff" share almost no
    letters, so no amount of fuzzy matching connects them - but on this campus
    they are one pastry at two counters."""
    known = ["chicken puff"]
    assert resolve_key("chicken patties", known) == ("chicken pattie", False)

    aliases = {"chicken pattie": "chicken puff"}
    assert resolve_key("chicken patties", known, aliases) == ("chicken puff", True)


def test_spelling_still_wins_before_any_alias_is_consulted():
    """An alias is a last resort. A name that already resolves on spelling must
    not be diverted by one."""
    known = ["chicken puff"]
    aliases = {"chicken puff": "masala tea"}  # a bad alias
    assert resolve_key("chkn puf", known, aliases) == ("chicken puff", True)


def test_an_alias_pointing_at_an_unpriced_item_is_ignored():
    """A reference can be deleted after an alias was approved. A stale alias
    must not resurrect a dead key and judge someone against nothing."""
    aliases = {"chicken pattie": "chicken puff"}
    assert resolve_key("chicken patties", ["masala tea"], aliases) == (
        "chicken pattie",
        False,
    )
