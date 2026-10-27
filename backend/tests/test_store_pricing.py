"""Price judging when the same item costs different amounts at different shops.

A single campus reference is wrong in both directions at once. It reads an
honest runner at the dearer canteen as persistently elevated, and it reads a
runner inflating at the cheaper one as normal — leaving the dishonest claim
better camouflaged than the honest one. These tests pin the behaviour that
fixes that, and the two bounds that keep the fix from becoming an attack.
"""

import uuid
from decimal import Decimal

import pytest

from app.modules.fraud import service as fraud
from app.modules.fraud.models import ReferencePrice
from app.modules.fraud.service import effective_tolerance

pytestmark = pytest.mark.asyncio


def _ref(price="20.00", tolerance="20.00", pct="0.400"):
    return ReferencePrice(
        reference_price=Decimal(price),
        band_min=Decimal("5.00"),
        band_max=Decimal("500.00"),
        tolerance_abs=Decimal(tolerance),
        tolerance_pct=Decimal(pct),
    )


# --------------------------------------------------------------- allowance


async def test_the_allowance_scales_with_the_item_price():
    """A flat rupee line cannot serve a canteen menu.

    ₹20 is +80% on a ₹25 puff and +4% on a ₹500 grocery run, so a flat line
    leaves cheap items — most of the traffic — effectively unprotected.
    """
    assert effective_tolerance(_ref("10.00")) == Decimal("5.00")   # floor
    assert effective_tolerance(_ref("20.00")) == Decimal("8.00")
    assert effective_tolerance(_ref("35.00")) == Decimal("14.00")
    assert effective_tolerance(_ref("500.00")) == Decimal("20.00")  # ceiling


async def test_a_cheap_item_tripled_is_now_flagged():
    """The case that motivated the change: ₹29 for a ₹10 tea was paid in full
    under the flat line, because ₹19 over sits under ₹20."""
    ref = _ref("10.00")
    assert fraud.judge(Decimal("29"), 1, ref).verdict == "FLAGGED"
    # A plausibly dearer shop is still not fraud.
    assert fraud.judge(Decimal("14"), 1, ref).verdict == "ELEVATED"


async def test_an_expensive_item_keeps_its_old_allowance():
    """The ceiling means large orders behave exactly as they did before."""
    ref = _ref("500.00")
    assert fraud.judge(Decimal("520"), 1, ref).verdict == "ELEVATED"
    assert fraud.judge(Decimal("521"), 1, ref).verdict == "FLAGGED"


async def test_zero_percent_falls_back_to_the_flat_ceiling():
    """An admin can disable scaling per item without a code change."""
    assert effective_tolerance(_ref("10.00", pct="0")) == Decimal("20.00")


# ------------------------------------------------------------------ store


async def test_an_unknown_store_is_judged_at_campus_prices():
    """A shop with no observed history is not a licence to charge anything.

    Passing db=None is deliberate: this branch must return before touching the
    database, and asserting that here means a future edit cannot quietly make
    the no-store path depend on a query.
    """
    ref = _ref("20.00")
    assert await fraud.store_adjusted_reference(
        None, uuid.uuid4(), "chicken puff", None, ref
    ) == Decimal("20.00")


async def test_store_drift_is_bounded_but_not_the_operative_control():
    """However much history a store accumulates it cannot become arbitrarily
    dear — but the clamp must not be what limits ordinary variation either.

    Set too tight it overrides the shrinkage and blocks the honest case: at
    0.60 a shop genuinely charging Rs22 against a Rs10 campus median stayed
    mispriced no matter how many independent runners reported it, and every one
    of them was flagged. The real control is independence, below.
    """
    assert fraud.STORE_MAX_DRIFT > Decimal("1"), (
        "too tight a clamp permanently misprices genuinely dearer shops"
    )
    assert fraud.STORE_MAX_DRIFT <= Decimal("3"), "still a bound, not a licence"
    assert fraud.STORE_MIN_RUNNERS >= 3, (
        "the defence is independence: fewer than three runners is not consensus"
    )
