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

DAY = {"MON": 0, "TUE": 1, "WED": 2, "THU": 3, "FRI": 4, "SAT": 5, "SUN": 6}


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


def resolve(codes: list[str]) -> tuple[list[tuple[int, int, int, str]], list[str]]:
    """Expand slot codes into concrete busy blocks.

    Returns (blocks, unknown) where each block is (day, start, end, label) and
    `unknown` lists any codes we didn't recognise. Duplicate blocks (same
    day+start) are collapsed so pasting a slot twice is harmless.
    """
    seen: set[tuple[int, int]] = set()
    blocks: list[tuple[int, int, int, str]] = []
    unknown: list[str] = []
    for raw in codes:
        code = raw.strip().upper()
        if not code:
            continue
        times = SLOT_TIMES.get(code)
        if times is None:
            unknown.append(code)
            continue
        for day, start, end in times:
            if (day, start) not in seen:
                seen.add((day, start))
                blocks.append((day, start, end, code))
    return blocks, unknown
