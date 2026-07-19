"""VIT Vellore FFCS slot catalogue.

Students are assigned course *slots* (A1, TB2, L11, …), not raw times — that's
what they read off VTOP. This module is the single source of truth mapping
each slot code to the concrete weekly time blocks it occupies, so a runner can
just enter their slots and we know exactly when they're in class.

Encoded directly from the university master timetable grid (theory + lab rows).
day_of_week: 0 = Monday (matches TimetableSlot). Times are minutes-from-midnight.

If the university revises slot timings, edit the column arrays / day sequences
below — nothing else needs to change.
"""

import re

DAY = {"MON": 0, "TUE": 1, "WED": 2, "THU": 3, "FRI": 4, "SAT": 5, "SUN": 6}

# What a slot code looks like: 1-4 letters then 1-2 digits (A1, TB2, TAA1, L11,
# V10, W22). Students don't hand us clean codes — they paste their whole VTOP
# "registered courses" page. Anything not matching this shape (prose, venues
# like SJT504, reg numbers, staff names, dates) is silently ignored so it never
# clutters the "didn't recognise" list; only slot-shaped-but-invalid codes do.
_SLOT_SHAPE = re.compile(r"^[A-Z]{1,4}\d{1,2}$")


def _m(h: int, mm: int) -> int:
    return h * 60 + mm


# Theory columns: 08:00, 09:00, 10:00, 11:00, 12:00 | 14:00, 15:00, 16:00,
# 17:00, 18:00 | 19:01 (the trailing V slot).
THEORY_COLS = [
    (_m(8, 0), _m(8, 50)),
    (_m(9, 0), _m(9, 50)),
    (_m(10, 0), _m(10, 50)),
    (_m(11, 0), _m(11, 50)),
    (_m(12, 0), _m(12, 50)),
    (_m(14, 0), _m(14, 50)),
    (_m(15, 0), _m(15, 50)),
    (_m(16, 0), _m(16, 50)),
    (_m(17, 0), _m(17, 50)),
    (_m(18, 0), _m(18, 50)),
    (_m(19, 1), _m(19, 50)),
]

# Lab columns: staggered 50-min blocks, morning six then afternoon six.
LAB_COLS = [
    (_m(8, 0), _m(8, 50)),
    (_m(8, 51), _m(9, 40)),
    (_m(9, 51), _m(10, 40)),
    (_m(10, 41), _m(11, 30)),
    (_m(11, 40), _m(12, 30)),
    (_m(12, 31), _m(13, 20)),
    (_m(14, 0), _m(14, 50)),
    (_m(14, 51), _m(15, 40)),
    (_m(15, 51), _m(16, 40)),
    (_m(16, 41), _m(17, 30)),
    (_m(17, 40), _m(18, 30)),
    (_m(18, 31), _m(19, 20)),
]

# Theory slot per day, in column order (11 columns; dashes/lunch omitted).
THEORY = {
    "MON": ["A1", "F1", "D1", "TB1", "TG1", "A2", "F2", "D2", "TB2", "TG2", "V3"],
    "TUE": ["B1", "G1", "E1", "TC1", "TAA1", "B2", "G2", "E2", "TC2", "TAA2", "V4"],
    "WED": ["C1", "A1", "F1", "V1", "V2", "C2", "A2", "F2", "TD2", "TBB2", "V5"],
    "THU": ["D1", "B1", "G1", "TE1", "TCC1", "D2", "B2", "G2", "TE2", "TCC2", "V6"],
    "FRI": ["E1", "C1", "TA1", "TF1", "TD1", "E2", "C2", "TA2", "TF2", "TDD2", "V7"],
    "SAT": ["V8", "X11", "X12", "Y11", "Y12", "X21", "Z21", "Y21", "W21", "W22", "V9"],
    "SUN": ["V10", "Y11", "Y12", "X11", "X12", "Y21", "Z21", "X21", "W21", "W22", "V11"],
}

# Lab slot per day, in column order (12 columns).
LAB = {
    "MON": ["L1", "L2", "L3", "L4", "L5", "L6", "L31", "L32", "L33", "L34", "L35", "L36"],
    "TUE": ["L7", "L8", "L9", "L10", "L11", "L12", "L37", "L38", "L39", "L40", "L41", "L42"],
    "WED": ["L13", "L14", "L15", "L16", "L17", "L18", "L43", "L44", "L45", "L46", "L47", "L48"],
    "THU": ["L19", "L20", "L21", "L22", "L23", "L24", "L49", "L50", "L51", "L52", "L53", "L54"],
    "FRI": ["L25", "L26", "L27", "L28", "L29", "L30", "L55", "L56", "L57", "L58", "L59", "L60"],
    "SAT": ["L71", "L72", "L73", "L74", "L75", "L76", "L77", "L78", "L79", "L80", "L81", "L82"],
    "SUN": ["L83", "L84", "L85", "L86", "L87", "L88", "L89", "L90", "L91", "L92", "L93", "L94"],
}

# slot code -> [(day_of_week, start_minute, end_minute), ...]
# A single theory slot (e.g. A1) recurs on multiple days — that's why it's a list.
SLOT_TIMES: dict[str, list[tuple[int, int, int]]] = {}
for _day, _seq in THEORY.items():
    for _i, _code in enumerate(_seq):
        SLOT_TIMES.setdefault(_code, []).append((DAY[_day], *THEORY_COLS[_i]))
for _day, _seq in LAB.items():
    for _i, _code in enumerate(_seq):
        SLOT_TIMES.setdefault(_code, []).append((DAY[_day], *LAB_COLS[_i]))


# A student's real class in the VTOP timetable GRID is annotated with its course
# code, e.g. "A2-BCSE307L-TH-SJT401-ALL" or "L1-BCSE308P-LO-SJT419-ALL". The
# glued "<SLOT>-<COURSE>" is what tells a booked cell apart from the hundred-odd
# empty grid labels ("A1", "V3", "L5") printed on the same page.
_ANNOTATED_SLOT = re.compile(
    r"\b([A-Z]{1,4}\d{1,2})-([A-Z]{3,4}\d{3}[A-Z])\b", re.IGNORECASE
)


def resolve_paste(text: str) -> tuple[list[tuple[int, int, int, str]], list[str]]:
    """Extract a timetable from whatever a student pastes out of VTOP.

    Two shapes come in, and they need opposite treatment:

    * **Timetable grid** — every one of the ~138 master slots is printed, but
      only the student's booked cells carry a course code ("D2-BCSE306L-…").
      Reading every bare label would mark them in class all week, so when we see
      any annotated cells we trust ONLY those, grouped by course.
    * **Registered-courses list** — slots appear as clubbed codes ("D1+TD1"),
      one per course row, with no slot⁠-course glue.

    Either way, a course's clubbed slots stay together as one label ("A1+TA1",
    "D2+TD2") — never fragmented into standalone A1 / TA1 rows. Returns
    (blocks, unknown); each block is (day, start, end, label).
    """
    annotated = [
        (m.group(1).upper(), m.group(2).upper()) for m in _ANNOTATED_SLOT.finditer(text)
    ]
    if annotated:
        # Grid: gather each course's booked slots, keep them as one group.
        by_course: dict[str, list[str]] = {}
        for slot, course in annotated:
            slots = by_course.setdefault(course, [])
            if slot not in slots:
                slots.append(slot)
        groups = [("+".join(sorted(slots)), slots) for slots in by_course.values()]
    else:
        # List: each whitespace token may be a clubbed group like "D1+TD1".
        groups = []
        for token in text.split():
            members = []
            for part in token.split("+"):
                code = re.sub(r"[^A-Za-z0-9]", "", part).upper()
                if _SLOT_SHAPE.match(code):
                    members.append(code)
            if members:
                groups.append(("+".join(members), members))
    return _expand_groups(groups)


def resolve(codes: list[str]) -> tuple[list[tuple[int, int, int, str]], list[str]]:
    """Expand bare slot codes into busy blocks — one label per code.

    Returns (blocks, unknown) where each block is (day, start, end, label) and
    `unknown` lists slot-shaped codes we didn't recognise.
    """
    groups = [(c.strip().upper(), [c.strip().upper()]) for c in codes if c.strip()]
    return _expand_groups(groups)


def _expand_groups(
    groups: list[tuple[str, list[str]]],
) -> tuple[list[tuple[int, int, int, str]], list[str]]:
    """Expand (label, [slot codes]) groups into concrete busy blocks.

    Every block a group produces carries the group's label, so a clubbed course
    reads as "A1+TA1" throughout. Duplicate (day, start) blocks are collapsed so
    pasting a slot twice is harmless; only slot-shaped-but-unknown codes are
    reported back.
    """
    seen: set[tuple[int, int]] = set()
    blocks: list[tuple[int, int, int, str]] = []
    unknown: list[str] = []
    for label, members in groups:
        for code in members:
            times = SLOT_TIMES.get(code)
            if times is None:
                if _SLOT_SHAPE.match(code):
                    unknown.append(code)
                continue
            for day, start, end in times:
                if (day, start) not in seen:
                    seen.add((day, start))
                    blocks.append((day, start, end, label))
    return blocks, unknown
