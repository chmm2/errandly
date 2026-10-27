# Internal build notes — apply when generating Chris's slides

Working notes only. Not a deliverable, not part of `chris-slides-plan.md`.
These are corrections and decisions settled in discussion after the plan was
written; fold them in at build time.

---

## Register: slide copy vs speaker detail

The plan document is written at **reference** level. Slide copy must be a
thinner layer on top of it.

**Rule: the slide carries the shape, the presenter carries the numbers.**
Thresholds are answers to questions, not the questions themselves. If nobody
asks, they are never said.

Rewrites agreed:

| Do not put on a slide | Put this instead |
|---|---|
| "gates at ≥4 friend ratings and ≥70% concentration, then any of three routes…" | "We only look if 4+ friends rated them and most ratings come from friends. Then three questions — any yes raises a flag." |
| "≥3 members, ≥2 laps, each leg substantial by value OR frequency" | "Three or more people. Money went round more than once. Each leg is real — big enough, or often enough." |
| "excess = observed − expected, standardised" | "What our app expected, versus what actually happened." |
| "ε-greedy socially-blind dispatch rounds" | "1 in 20 errands, we ignore friendship completely." |
| "confidence shrinkage — thin profile pulled toward neutral" | "A few ratings barely move your score. You have to earn your way up." |

The three farming routes as slide copy — plain questions, no numbers:

1. Do friends rate them much higher than strangers?
2. Did friends rush to rate them right after they were penalised?
3. Has *any* stranger ever rated them?

---

## Corrections to fold in

### 1. Penalty is severity × decay, not a fixed number

`totals[user_id] += weight * decay(age_days)` — integrity.py:143.

So never write "severity 2 → 700 m" as though fixed. Correct phrasing:

> **A farming flag starts at 700 m and fades to nothing over 30 days.**
> **A ring flag starts at 1200 m and does the same.**

Also: capped at 2000 m total across all flags, and `penalties()` fails open —
returns None on error, so a lookup failure never demotes anyone.

### 2. Rating farming DOES carry a penalty — two of them

Earlier phrasing ("the real penalty already happened in the always-on layer")
left the impression there is no penalty. Wrong. Both apply, on two different
lines of the same expression:

- **errands/service.py:388** — `− (rep − 3.5) × 800`. The farmed reputation is
  discounted to ~3.55, so they get ~44 m instead of the ~1040 m they were
  farming for. Automatic, no flag needed.
- **errands/service.py:389** — `+ penalty`. Once flagged, 700 m × decay.

Slide line: *"Farming is punished twice — the reputation they farmed is
discounted to nearly nothing, and the flag pushes them 700 m down the queue."*

### 3. The flag trigger is one function returning non-None

`farming_signals(profile)` returns `None` unless **both gates pass AND at least
one route fires**. Non-None → flag row → penalty applies from the next errand.

**No flag → no penalty. The gates are the trigger.** Worth stating plainly,
because it was asked twice.

### 4. Nothing is "administered"

There is no moment of applying a penalty and no field written on the user.
`penalties()` is called at line 231 on **every dispatch**, queried fresh from
the flags table. Live from the next errand after a flag appears; gone from the
next errand after dismissal. Same derived-not-stored pattern as the wallet
balance — worth drawing the parallel.

### 5. Worked example that actually fires

Use the patient farmer, since it is measured and it fires:

- 20 ratings from 5 friends, 1 from anyone else
- Gate 1: 20 ≥ 4 ✅ · Gate 2: 95% ≥ 70% ✅
- Routes 1 and 2 cannot fire (no strangers to compare, no prior penalty)
- Route 3 fires → *"a reputation no stranger has ever tested"*

And the contrast that does NOT fire — Karan at 12 friend / 8 stranger ratings,
concentration 60%, below the gate. That is the known hole; state it as
Project-II rather than let it be found.

### 6. Confidence shrinkage table

Everyone below has a perfect 5.0 average — only the number of ratings differs:

| Effective votes | Score they get |
|---|---|
| 0.25 | **3.55** |
| 1 | 3.67 |
| 4 | 4.00 |
| 20 | 4.57 |
| 50 | 4.79 |

The 3.55 row is exactly the ten-fake-ratings result. Good single slide visual.

---

## Open questions still unanswered by Chris

1. Slide order — rings before exploration/z (proposed), or original order?
2. Keep both added slides (the flaw slide, the penalty slide)?
3. Is rating farming Chris's or Ujjwal's? Collision risk in the split.

Do not build until these are answered.

---

## Slide 2 (Collusion Rings) — replace the "hole we found" beat

Chris's call: **drop the zero-rupee value-floor story from the slide.** The fix
stays in the code and the tests; it is just not what that slide should spend its
time on. Keep it as a speaker answer only if somebody asks how the floors were
chosen.

Replace it with the question the panel will actually have: **how do you tell an
honest group from one that only ever deals with itself?**

### The framing to use — four filters, one human

The honest answer is that no single test separates them. Each filter clears a
different kind of innocent group, and whoever survives all four gets a person.

| Filter | What it asks | Clears | Still misses |
|---|---|---|---|
| 1. Structure | Is the group closed? | **nobody** — a friend group and a ring are the same shape (closure 1.0) | everyone |
| 2. Money cycle | Does value leave the group? | ordinary friend groups who also run errands for strangers | a genuinely insular group |
| 3. z | Did our own app cause it? | insular groups who simply accept what they are offered | a group who deliberately prefer each other |
| 4. LLM | Do the errands read real? | genuine roommates — varied shops, odd hours, real notes | a careful ring that writes varied titles |
| 5. Human | — | — | — |

Filter 1 is where naive detection stops, and it is exactly why the naive metric
flags **6 of 6 honest groups**. Use that number here.

**Line for the slide:**

> No single test separates them. Each filter clears a different kind of innocent
> group, and whoever survives all four gets a human — not a ban.

Stronger than claiming a clean separator, and true. It also explains why the
pipeline has four stages rather than one, which otherwise looks like
over-engineering.

### Do NOT put on the slide

The iterative-vs-recursive Tarjan detail. It is an implementation decision, not
a contribution, and it costs screen space that the four-filter table needs.

Keep it as a prepared answer to "does this scale?":

> "Tarjan is normally written recursively, which caps out around a thousand deep
> in Python. The depth is the longest payment chain in the graph, and on a
> campus of four thousand users that is reachable. We wrote it iteratively so
> graph size cannot crash the detector."

Worth having ready — a crash in a background worker would take out ring
detection and farming detection together, silently.
