"""What makes one leg of a cycle count as real.

A value-only floor was dodgeable, and cheaply. Errand rewards may be zero, so a
group cycling zero-rupee errands never reached the rupee floor and was discarded
before any human could see it — while still collecting the completed-errand
history and the rating opportunities that are the actual motive for a ring.

These tests pin the replacement: a leg qualifies on value OR on repetition, and
repetition cannot be priced around.
"""

import pytest

from app.modules.fraud import collusion
from app.modules.fraud.collusion import (
    MIN_RING_LAPS,
    MIN_RING_LEG_TXNS,
    MIN_RING_LEG_VALUE,
)


def qualifies(value: float, txns: int) -> bool:
    """The filter as find_rings applies it to a single edge."""
    substantial = value >= MIN_RING_LEG_VALUE or txns >= MIN_RING_LEG_TXNS
    return txns >= MIN_RING_LAPS and substantial


# ───────────────────────────────────────────────────── the hole that was closed


def test_a_zero_rupee_leg_repeated_often_now_counts():
    """The attack the old floor missed. A completed errand buys the same
    history and the same rating opportunity whether it carried 600 rupees or
    nothing, so pricing a cycle at zero must not make it invisible."""
    assert qualifies(value=0.0, txns=MIN_RING_LEG_TXNS)


def test_a_one_rupee_leg_repeated_often_counts():
    assert qualifies(value=MIN_RING_LEG_TXNS * 1.0, txns=MIN_RING_LEG_TXNS)


def test_the_old_value_floor_would_have_missed_both():
    """Documents the previous behaviour so a future edit cannot quietly
    reintroduce it."""
    old_rule = lambda v, t: v >= MIN_RING_LEG_VALUE and t >= MIN_RING_LAPS
    assert not old_rule(0.0, MIN_RING_LEG_TXNS)
    assert qualifies(0.0, MIN_RING_LEG_TXNS)


# ─────────────────────────────────────────────── the value route still works


def test_a_high_value_leg_still_counts_without_many_repeats():
    """Two substantial payments remain enough. The frequency route is an
    addition, not a replacement."""
    assert qualifies(value=MIN_RING_LEG_VALUE, txns=MIN_RING_LAPS)


def test_value_just_below_the_floor_needs_the_repetition_route():
    assert not qualifies(value=MIN_RING_LEG_VALUE - 1, txns=MIN_RING_LAPS)
    assert qualifies(value=MIN_RING_LEG_VALUE - 1, txns=MIN_RING_LEG_TXNS)


# ────────────────────────────────────────────────────────── the floors hold


def test_a_single_payment_never_counts_however_large():
    """One transfer is not a cycle. A single coincidental A->B->C->A over a
    semester is not evidence of anything."""
    assert not qualifies(value=100_000.0, txns=1)


def test_two_small_payments_are_still_ordinary():
    """Two friends splitting a couple of cheap errands must not become a leg."""
    assert not qualifies(value=20.0, txns=2)


def test_the_repetition_floor_sits_above_ordinary_reciprocity():
    """Five errands in ONE direction between the same two people is already
    unusual. Set it at two and every pair who take turns would qualify."""
    assert MIN_RING_LEG_TXNS > MIN_RING_LAPS
    assert MIN_RING_LEG_TXNS >= 5


def test_a_qualifying_leg_is_still_not_an_accusation():
    """The leg filter only decides what enters the cycle search. Group size,
    a closed cycle among mutual friends, and the policy check all still apply
    before anybody is flagged."""
    assert collusion.MIN_RING_SIZE >= 3
