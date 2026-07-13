import pytest

from app.modules.timetable import vit_slots

pytestmark = pytest.mark.asyncio(loop_scope="session")

NEAR = {"lat": 12.9692, "lng": 79.1559}


# --------------------------------------------------------------- unit: catalog

async def test_theory_slot_recurs_across_days():
    # A1 is Monday 08:00 AND Wednesday 09:00 in the VIT grid.
    blocks = vit_slots.SLOT_TIMES["A1"]
    assert (0, 480, 530) in blocks  # Mon 08:00–08:50
    assert (2, 540, 590) in blocks  # Wed 09:00–09:50


async def test_lab_slot_single_block():
    # L11 is Tuesday, morning 5th lab column (11:40–12:30).
    assert vit_slots.SLOT_TIMES["L11"] == [(1, 700, 750)]


async def test_resolve_expands_and_flags_unknown():
    blocks, unknown = vit_slots.resolve(["B2", "TB2", "L11", "ZZ9", "a1"])
    assert "ZZ9" in unknown
    days_starts = {(d, s) for d, s, _e, _l in blocks}
    assert (2, 540) in days_starts  # case-insensitive a1 → Wed 09:00
    # no duplicate (day, start) blocks
    assert len(blocks) == len(days_starts)


# ------------------------------------------------------------- endpoint: PUT

async def test_put_vit_slots_replaces_timetable(client, make_user):
    _, headers = await make_user("Runner")

    resp = await client.put(
        "/timetable/vit", json={"codes": ["B2", "TB2", "L11", "NOPE"]}, headers=headers
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["unknown"] == ["NOPE"]
    labels = {s["label"] for s in body["slots"]}
    assert {"B2", "TB2", "L11"} <= labels

    # Re-submitting a different set REPLACES (not appends)
    resp2 = await client.put("/timetable/vit", json={"codes": ["A1"]}, headers=headers)
    assert resp2.status_code == 200
    labels2 = {s["label"] for s in resp2.json()["slots"]}
    assert labels2 == {"A1"}  # B2/TB2/L11 gone

    listing = (await client.get("/timetable", headers=headers)).json()
    assert {s["label"] for s in listing} == {"A1"}


async def test_put_vit_slots_all_unknown_rejected(client, make_user):
    _, headers = await make_user("Runner")
    resp = await client.put("/timetable/vit", json={"codes": ["XYZ", "???"]}, headers=headers)
    assert resp.status_code == 400


async def test_vit_class_blocks_going_online(client, make_user):
    """A resolved VIT slot covering 'now' must block runner mode, proving the
    catalogue feeds the existing enforcement path."""
    from app.modules.timetable.service import _campus_now

    _, headers = await make_user("Busy Student")
    day, minute = _campus_now()

    # Find a real slot code whose block covers the current campus time.
    covering = None
    for code, times in vit_slots.SLOT_TIMES.items():
        if any(d == day and s <= minute < e for d, s, e in times):
            covering = code
            break
    if covering is None:
        pytest.skip("no VIT slot covers the current time of day")

    resp = await client.put("/timetable/vit", json={"codes": [covering]}, headers=headers)
    assert resp.status_code == 200, resp.text

    blocked = await client.post(
        "/runners/me/availability", json={"is_available": True, **NEAR}, headers=headers
    )
    assert blocked.status_code == 409
