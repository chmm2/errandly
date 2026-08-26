"""Collusion detection over PAID edges.

Two layers, tested separately:

  * the scoring maths, which decides how hard to discount a neighbourhood —
    pure, no graph, and the part where a wrong constant silently punishes
    innocent people;
  * the Cypher, run against the real Neo4j, because a query that returns the
    wrong shape is invisible to any amount of unit testing.
"""

import uuid

import pytest

from app.core.graph import run_write
from app.modules.fraud import collusion
from app.modules.social.service import (
    MAX_CLOSURE_PENALTY,
    MAX_CORROBORATED_PENALTY,
    _closure_penalty,
    _direct_penalty,
)

graph_test = pytest.mark.asyncio(loop_scope="session")


# ------------------------------------------------------------ scoring maths


def test_circulation_below_the_knee_is_ignored():
    """Students really do run errands for their friends. That must stay
    unremarkable, or the detector fires on ordinary campus life."""
    assert collusion.circulation_penalty(0.0) == 0.0
    assert collusion.circulation_penalty(0.5) == 0.0
    assert collusion.circulation_penalty(collusion.CIRCULATION_KNEE) == 0.0


def test_circulation_ramps_rather_than_switching_on():
    just_over = collusion.circulation_penalty(collusion.CIRCULATION_KNEE + 0.01)
    assert 0.0 < just_over < 0.1, "a hair over the knee is a nudge, not a verdict"
    assert collusion.circulation_penalty(1.0) == 1.0


def test_an_open_group_is_never_penalised_however_much_it_transacts():
    """The conjunction that matters is closed AND circulating. A sociable hub
    whose friends all know outsiders is not a ring no matter how much money
    moves through it."""
    assert _closure_penalty(closure=0.0, degree=8, circulation=1.0) == 0.0
    assert _closure_penalty(closure=0.3, degree=5, circulation=0.95) == 0.0


def test_a_closed_group_with_no_money_flow_keeps_the_structural_cap():
    """Structure alone asks the question; it does not answer it. Without
    money-flow evidence the discount must stay at the prior."""
    penalty = _closure_penalty(closure=1.0, degree=4, circulation=0.0)
    assert penalty == pytest.approx(MAX_CLOSURE_PENALTY)


def test_money_circulating_in_a_closed_group_escalates_the_discount():
    """The whole point: the same shape, judged harder once value is shown to
    go round inside it."""
    structural = _closure_penalty(closure=1.0, degree=4, circulation=0.0)
    corroborated = _closure_penalty(closure=1.0, degree=4, circulation=1.0)

    assert corroborated > structural
    assert corroborated == pytest.approx(MAX_CORROBORATED_PENALTY)


def test_the_discount_never_reaches_total_exclusion():
    """Even a corroborated ring may contain someone who simply has friends.
    A 1.0 would erase them from matching entirely."""
    worst = _closure_penalty(closure=1.0, degree=10, circulation=1.0)
    assert worst < 1.0


def test_a_lone_user_is_never_penalised():
    assert _closure_penalty(closure=1.0, degree=1, circulation=1.0) == 0.0


def test_a_close_friend_group_is_not_penalised_on_shape_alone():
    """The case this must never break: four students who are genuinely close.
    Maximum closure, no money circulating. A direct friend stays a full-trust
    direct friend."""
    assert _direct_penalty(closure=1.0, degree=4, circulation=0.0) == 0.0
    assert _direct_penalty(closure=1.0, degree=4, circulation=0.5) == 0.0


def test_a_direct_friend_in_a_circulating_ring_is_discounted():
    """The hole this closes. In a 3-person ring every member is one hop from
    every other, so the intermediary-based penalty never fired and the ranker
    offered ring members each other's errands at full trust."""
    penalty = _direct_penalty(closure=1.0, degree=2, circulation=1.0)
    assert penalty == pytest.approx(MAX_CORROBORATED_PENALTY)


def test_circulation_without_closure_barely_touches_a_direct_friend():
    """Someone who trades a lot with friends but whose friends all know the
    wider campus is not a ring — the group has no walls to hide behind."""
    assert _direct_penalty(closure=0.1, degree=6, circulation=1.0) < 0.1


# ------------------------------------------------------------------- Cypher


async def _wipe_graph():
    await run_write("MATCH (n:User) DETACH DELETE n")


async def _friends(a: str, b: str):
    await run_write(
        "MERGE (x:User {id:$a}) MERGE (y:User {id:$b}) MERGE (x)-[:FRIEND]-(y)", a=a, b=b
    )


async def _paid(a: str, b: str, amount: float, errand: str):
    await run_write(
        """
        MATCH (x:User {id:$a}), (y:User {id:$b})
        MERGE (x)-[p:PAID {errand_id:$e}]->(y)
        ON CREATE SET p.amount = $amt
        """,
        a=a, b=b, e=errand, amt=amount,
    )


async def _make_ring(members: list[str], laps: int, amount: float):
    """Wire members into a friend clique with money going round it `laps` times."""
    for i, m in enumerate(members):
        await _friends(m, members[(i + 1) % len(members)])
    for lap in range(laps):
        for i, m in enumerate(members):
            await _paid(
                m, members[(i + 1) % len(members)], amount, f"{m[:4]}-{lap}"
            )


@graph_test
async def test_a_closed_money_cycle_is_detected():
    """Three mutual friends paying round in a circle, repeatedly. This is the
    shape structure alone could not distinguish from a genuine friend group."""
    await _wipe_graph()
    members = [str(uuid.uuid4()) for _ in range(3)]
    await _make_ring(members, laps=3, amount=400)

    rings = await collusion.find_rings()

    assert len(rings) == 1, "one cycle, one finding — not three rotations"
    found = rings[0]
    assert set(str(m) for m in found.members) == set(members)
    assert found.laps == 3
    assert found.size == 3


@graph_test
async def test_friends_who_never_pay_each_other_are_not_a_ring():
    """The control. Same closed friend triangle, no money moving inside it —
    which is what an ordinary group of friends looks like."""
    await _wipe_graph()
    a, b, c = (str(uuid.uuid4()) for _ in range(3))
    await _friends(a, b)
    await _friends(b, c)
    await _friends(c, a)

    assert await collusion.find_rings() == []


@graph_test
async def test_money_going_round_strangers_is_not_a_ring():
    """Three people who paid each other in a circle but are not friends. Odd,
    but without the closed social shape it is not the pattern we are naming."""
    await _wipe_graph()
    members = [str(uuid.uuid4()) for _ in range(3)]
    for lap in range(3):
        for i, m in enumerate(members):
            await _paid(m, members[(i + 1) % len(members)], 400, f"{m[:4]}-{lap}")

    assert await collusion.find_rings() == []


@graph_test
async def test_a_single_lap_is_not_enough():
    """One coincidental circuit over a semester is not evidence."""
    await _wipe_graph()
    members = [str(uuid.uuid4()) for _ in range(3)]
    await _make_ring(members, laps=1, amount=400)

    assert await collusion.find_rings() == []


@graph_test
async def test_trivial_amounts_do_not_make_a_ring():
    """Every leg has to carry real money, or three friends splitting chai
    becomes a fraud finding."""
    await _wipe_graph()
    members = [str(uuid.uuid4()) for _ in range(3)]
    await _make_ring(members, laps=4, amount=10)

    assert await collusion.find_rings() == []


@graph_test
async def test_circulation_is_measured_and_stored():
    """A ring's members should read as almost entirely internal; someone who
    trades with the wider campus should not."""
    await _wipe_graph()
    ring = [str(uuid.uuid4()) for _ in range(3)]
    await _make_ring(ring, laps=3, amount=400)

    # An outsider who transacts with one ring member and several strangers.
    outsider = str(uuid.uuid4())
    strangers = [str(uuid.uuid4()) for _ in range(4)]
    await _friends(outsider, ring[0])
    await _paid(outsider, ring[0], 200, "out-1")
    for i, s in enumerate(strangers):
        await _paid(outsider, s, 400, f"out-s{i}")

    await collusion.refresh_circulation()
    scores = await collusion.circulation_for(
        [uuid.UUID(ring[0]), uuid.UUID(outsider)]
    )

    assert scores[uuid.UUID(ring[0])] > 0.9, "the ring's money barely leaves it"
    assert scores[uuid.UUID(outsider)] < collusion.CIRCULATION_KNEE, (
        "someone trading across campus must stay below the knee"
    )


@graph_test
async def test_circulation_ignores_users_with_too_little_history():
    """Two errands, both for a friend, reads as 100% internal — and means
    nothing. A new student must not start out looking like a ring."""
    await _wipe_graph()
    a, b = str(uuid.uuid4()), str(uuid.uuid4())
    await _friends(a, b)
    await _paid(a, b, 50, "e1")

    await collusion.refresh_circulation()
    scores = await collusion.circulation_for([uuid.UUID(a)])

    assert scores[uuid.UUID(a)] == 0.0
