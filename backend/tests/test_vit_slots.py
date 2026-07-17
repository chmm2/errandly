# ruff: noqa: E501 — grid fixtures below are pasted VTOP rows; they're long by nature.
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
    assert "ZZ9" in unknown  # slot-shaped but not real → flagged
    days_starts = {(d, s) for d, s, _e, _l in blocks}
    assert (2, 540) in days_starts  # case-insensitive a1 → Wed 09:00
    # no duplicate (day, start) blocks
    assert len(blocks) == len(days_starts)


async def test_resolve_ignores_non_slot_prose():
    # Prose, venues, reg numbers, names, dates — none look like a slot, so they
    # are dropped silently; only the genuinely slot-shaped "ZZ9" is flagged.
    _blocks, unknown = vit_slots.resolve(
        ["General", "BCSE317L", "SJT504", "MOHD", "2026", "NIL", "ZZ9"]
    )
    assert unknown == ["ZZ9"]


GRID_PASTE = """
MON	THEORY	A1	F1	D1	TB1	TG1	-	Lunch	A2-BCSE307L-TH-SJT401-ALL	F2-BCSE308L-TH-SJT301-ALL	D2-BCSE306L-TH-SJT603-ALL	TB2-BCSE302L-TH-SJT308-ALL	TG2-BCSE355L-TH-SJT303-ALL	-	V3
LAB	L1-BCSE308P-LO-SJT419-ALL	L2-BCSE308P-LO-SJT419-ALL	L3-BCSE303P-LO-SJT317-ALL	L4-BCSE303P-LO-SJT317-ALL	L5	L6	Lunch	L31	L32	L33	L34	L35	L36	-
TUE	THEORY	B1	G1	E1	TC1	TAA1	-	Lunch	B2-BCSE302L-TH-SJT308-ALL	G2-BCSE355L-TH-SJT303-ALL	E2-BSTS301P-SS-SJT603-ALL	TC2-BCSE303L-TH-SJT315-ALL	TAA2	-	V4
LAB	L7	L8	L9	L10	L11-BCSE302P-LO-SJT416-ALL	L12-BCSE302P-LO-SJT416-ALL	Lunch	L37	L38	L39	L40	L41	L42	-
"""


async def test_resolve_paste_grid_takes_only_annotated():
    """Pasting the VTOP timetable grid must pull ONLY the course-annotated
    cells — never the bare grid labels (A1, F1, V3, L5) that fill every page —
    and keep each course's clubbed slots together as one label."""
    blocks, unknown = vit_slots.resolve_paste(GRID_PASTE)
    labels = {label for _d, _s, _e, label in blocks}
    # Clubbed by course: DB = B2+TB2, DB-lab = L11+L12, CN-lab = L1+L2, etc.
    assert "B2+TB2" in labels
    assert "G2+TG2" in labels
    assert "L1+L2" in labels
    assert "L11+L12" in labels
    # A clubbed slot must never appear split into its own standalone entry.
    for split in ("A1", "F1", "TB1", "V3", "L5", "TB2", "B2"):
        assert split not in labels
    assert unknown == []


async def test_resolve_paste_list_keeps_clubbed_slots():
    """The registered-courses list has clubbed codes ("D1+TD1") — they must
    stay clubbed, not split into standalone D1 / TD1 entries."""
    blob = "2 BCSE317L - Information Security D1+TD1 - SJT504 RAMANI S 3 A1+TA1 - SJT503"
    blocks, _unknown = vit_slots.resolve_paste(blob)
    labels = {label for _d, _s, _e, label in blocks}
    assert labels == {"D1+TD1", "A1+TA1"}
    assert "D1" not in labels and "TA1" not in labels


async def test_resolve_from_pasted_vtop_page():
    """The real ask: a student pastes their whole VTOP 'registered courses'
    page and we pull out exactly the slots, with nothing flagged as unknown."""
    blob = """
    2  General (Semester)  BCSE317L - Information Security  ( Theory Only )
       3 0 0 0 3.0   Discipline Elective  Regular  VL2026270102083
       D1+TD1 -  SJT504  RAMANI S -  SCOPE  28-Jun-2026 12:00  Registered and Approved
    3  BCSE324L - Foundations of Blockchain Technology  A1+TA1 -  SJT503  THANUJA R
    4  BCSE406L - NoSQL Databases  B1+TB1 -  SJT619  ADALINE SUJI R
    5  BCSE497J - Project - I  ( Project )  NIL -  NIL  ACADEMICS
    1  BARB101L - Arabic  D2 -  PRP339  MOHD SAQIB -  SSL  07-Jul-2026 10:32
    """
    blocks, unknown = vit_slots.resolve_paste(blob)
    labels = {label for _d, _s, _e, label in blocks}
    assert labels == {"D1+TD1", "A1+TA1", "B1+TB1", "D2"}
    assert unknown == []


# ------------------------------------------------------------- endpoint: PUT

async def test_put_vit_slots_replaces_timetable(client, make_user):
    _, headers = await make_user("Runner")

    resp = await client.put(
        "/timetable/vit",
        # "SJT504" (a venue) is prose we drop; "ZZ9" is slot-shaped junk we flag.
        json={"codes": ["B2", "TB2", "L11", "SJT504", "ZZ9"]},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["unknown"] == ["ZZ9"]
    labels = {s["label"] for s in body["slots"]}
    assert {"B2", "TB2", "L11"} <= labels

    # Re-submitting a different set REPLACES (not appends)
    resp2 = await client.put("/timetable/vit", json={"codes": ["A1"]}, headers=headers)
    assert resp2.status_code == 200
    labels2 = {s["label"] for s in resp2.json()["slots"]}
    assert labels2 == {"A1"}  # B2/TB2/L11 gone

    listing = (await client.get("/timetable", headers=headers)).json()
    assert {s["label"] for s in listing} == {"A1"}


async def test_put_vit_slots_from_raw_grid(client, make_user):
    """Pasting the raw VTOP grid saves only the booked (annotated) slots, not
    every label on the grid — otherwise runner mode would lock all week."""
    _, headers = await make_user("Grid Paster")
    resp = await client.put("/timetable/vit", json={"raw": GRID_PASTE}, headers=headers)
    assert resp.status_code == 200, resp.text
    labels = {s["label"] for s in resp.json()["slots"]}
    assert "B2+TB2" in labels and "L11+L12" in labels  # booked cells, kept clubbed
    assert "A1" not in labels and "V3" not in labels  # bare grid labels excluded


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
