# Chris — slide plan for Review 2

Eight slides. Each one follows the same shape, because that is what a panel is
marking:

> **the gap in prior work  →  what we built  →  proof it works  →  what it costs the offender**

Every "verified" line below is something actually measured, and each is tagged:

- **[LIVE]** — measured on the running stack (real Neo4j, Redis, Postgres)
- **[SIM]** — simulation on a synthetic campus, parameters stated
- **[TEST]** — enforced by an automated test in the suite

---

## A note on ordering

Your list was: exploration → offer log/z → rings → LLM → farming.

I would reorder. Exploration and z **cannot be explained before rings**, because
the problem they solve only exists once you have a matcher *and* a ring
detector. Told in your order the panel hears the solution before the problem.

Proposed order below. Same five topics, plus a problem slide and a penalty
slide. Say the word if you'd rather keep yours.

---

## Slide 1 — Rating Farming

**Title:** Reputation Farming — and why volume cannot buy it

### The gap
[8] Kamvar et al., *EigenTrust*, WWW 2003 — the canonical reputation algorithm.
Its own authors state it is vulnerable to **collusive groups who rate each other
up**. The weakness is named and left unsolved.

[2] Chiou & Tu, IEEE Access 2020 — weights a rating by how close the rater is to
you. Closeness only ever **increases** weight. Correct for the honest case,
exactly backwards for the adversarial one: a reputation built entirely inside
your own circle is the signature of manipulation.

### What we built
Two layers.

**Always-on (no flag, no admin):**
- **One rater, one vote** — a friend who rates you ten times contributes one
  averaged opinion
- **Friend ratings discounted as concentration rises** — 1.00 at 50%, 0.25 at 100%
- **Confidence shrinkage** — a thin profile is pulled toward neutral 3.5

**The flag:** gates at ≥4 friend ratings and ≥70% concentration, then any of
three routes — friend/stranger gap ≥0.8 stars, a burst of in-circle praise
within 14 days of a penalty, or 15+ friend ratings with ≤1 from anyone else.

### Verified
- **[LIVE]** Ten fake five-star ratings from one friend moved a runner from
  **3.50 to 3.55**. The discount alone made the attack worthless — no detection
  required.
- **[LIVE]** At 100% concentration a friend's vote is worth **0.25**; a
  stranger's is always **1.00**.
- **[LIVE]** Before one-rater-one-vote: **100 farmed ratings scored 4.64 against
  4.57 for 20 honest stranger ratings** — patience beat the discount. Counting
  people instead of ratings removed it at the root.
- **[TEST]** Honest popular runner (friends 4.7 / strangers 4.7) is **not**
  flagged; the farmer (5.0 / 3.4) is.

### Penalty
Severity 2 → **+700 m** in matching. But the real penalty already happened in
the always-on layer, before any flag existed.

### Honest limitation to state
The post-penalty burst route sits **behind** the concentration gate, and a
runner with real stranger history cannot reach 70% without implausible farming.
So the exact attack that route describes is often unreachable. Fix is to compute
concentration over a recent window. **Not done — named as Project-II.**

### Image
`fig_farming.png` — NEW. Two columns: Karan (friends 5.0 / strangers 3.4, gap
1.6) vs Meera (4.7 / 4.7, no gap). Below: the discount curve, 1.00 → 0.25.

---

## Slide 2 — Collusion Rings

**Title:** When the group is the offender

### The gap
Rating farming catches one person. But farming is done by a **circle**, and
[8] leaves group collusion explicitly unsolved.

[9] Viswanath et al., ACM SIGCOMM 2010 — unifies the social-graph defences
(SybilGuard, SybilLimit, SybilRank) and shows they are really community
detection. Their effectiveness rests entirely on the graph being a faithful
**observation** of reality.

### What we built
A ring is a **directed payment cycle among mutual friends**.

- Cypher pulls `PAID` edges where both ends are friends, aggregated to one arrow
  per pair carrying `value` and `txns`
- **Tarjan's algorithm** finds strongly connected components — sets where
  everyone can reach everyone by following arrows. That *is* a money circle.
- Iterative, not recursive: stack depth equals the longest path, and a campus
  graph can exceed Python's limit. A detector that raises RecursionError is
  worse than one that is longer to read.
- Floors: **≥3 members**, **≥2 laps**, and each leg substantial **by value OR
  frequency**

### Verified
- **[LIVE]** Seeded a real 3-person ring (₹600, 2 laps). Sweep raised **3 flags,
  severity 3**, `closure = 1.0`. Sweep on honest data returns **0**.
- **[LIVE]** A pair is never a ring — `MIN_RING_SIZE = 3`, because two friends
  alternating lunch is the most ordinary thing on campus.
- **[TEST]** 9 tests on the leg floor alone.

### The hole we found and closed — worth a whole beat
The value floor was **dodgeable**. Errand rewards may be **zero** (`reward >= 0`
in schema and DB). So a ring cycling ₹0 errands never reached the ₹150 floor and
was **discarded before any human could see it** — while still collecting the
completed-errand history and rating opportunities that are the actual motive.

We floored the wrong thing. The motive is **reputation, not money**. Replaced
with: a leg qualifies by value **or** by frequency (≥5 in one direction).
Frequency cannot be priced around.

- **[TEST]** A test records the *old* rule and asserts it would have missed the
  ₹0 case, so it cannot be quietly reintroduced.

### Penalty
Severity 3 → **+1200 m**, **and** the members stop being offered each other's
errands. That exclusion is what actually breaks the circle.

### Image
`fig_social.png` — EXISTING. Honest group vs ring, identical structure, only the
money direction differs.

---

## Slide 3 — The Flaw We Found In Our Own System

**Title:** The platform manufactures its own evidence

*This is the slide the contribution rests on. It should feel like a problem
statement, not a solution.*

### The setup
[4] Cheng, Chen & Ye, IEEE ICDE 2019 — cooperation-aware assignment
deliberately co-assigns people who have worked together successfully. Measurable
quality gains. **The policy decides who transacts with whom, and that effect is
never examined.**

Our matcher does the same: a friend gets a **1500 m head start**.

### The collision
Ring detection reads "friends transacting with each other" as evidence.
Our matcher **causes** friends to transact with each other.

So the detector reads our own routing decisions back as evidence of fraud. And
it is worst for exactly the tight-knit groups it watches most closely — closure
and circulation end up correlated **through the routing policy**, not through
fraud.

### Verified
- **[SIM]** 60 students, 6000 errands, 6 honest friend groups in hostel blocks,
  1 real ring. At our deployed setting the naive metric flags **6 of 6 honest
  groups**. Every innocent group accused.
- **[SIM]** As the boost rises, the matcher's own expectation saturates:

| Boost | Matcher expects in-group | Ring's z | Caught? |
|---|---|---|---|
| 0 m | 40% | 27.0 | yes |
| 750 m | 88% | 8.1 | yes |
| **1500 m (ours)** | **99%** | **2.3** | **NO** |
| 2500 m | 100% | 0.6 | no |

**A strong enough trust boost makes collusion undetectable in principle** — not
because the ring hid, but because the router does the ring's job for it.

### Prior work does not address this
[9] and the Sybil literature assume an **exogenous** graph — something the
platform observes. Ours is **endogenous**: generated by our own decisions.
[10] Perdomo et al., ICML 2020 (*performative prediction*) is exactly the right
apparatus and has been developed for prediction and pricing, **never for fraud
evidence**.

### Image
`fig_flaw.png` — NEW. Left: matcher pushes friends together. Right: detector
reads that as fraud. A loop arrow between them labelled "we caused this."
Below: the saturation table as a small line chart, ring z falling 27 → 0.6.

---

## Slide 4 — The Offer Log

**Title:** Recording why each runner was offered an errand

### The gap
[7] Maranzato & Pereira, IEEE LA-Web 2009 — extracts behavioural features and
scores sellers, but **retrospectively**. Nothing records *why the platform made
the choice it made*, so the platform's own contribution to an observed pattern
can never be subtracted.

### What we built
Every dispatch round writes one row: the candidate set, each candidate's
**distance, trust, hops, reputation, penalty and final score**, whether the
round was socially blind, and who accepted.

Three design points worth defending:
- **Every term stored, not just the score** — a composite score cannot be
  decomposed, so "how would this have ranked without the social term?" would be
  unanswerable from the score alone
- **One row per dispatch round** — a re-offer happens under a different
  candidate set; collapsing rounds averages away the variation
- **Best-effort, in a SAVEPOINT** — analytics on a dispatch path must never stop
  an errand going out

### Verified
- **[LIVE]** 30 rows written during a test run, JSONB inspected and populated
- **[TEST]** Sabotage the writer → the errand is still created **and still
  acceptable**
- **[TEST]** `_terms_for` is the single source of truth, shared by ranker and
  log, so the two cannot drift

### The bug this caught
The exploring branch was **ordering** candidates with trust zeroed but
**logging** the boosted score — a friend recorded at `effective 1764` on a round
ranked as if their trust were zero. A stored score that contradicts the ordering
it explains would be inherited silently by every estimate built on it. Found by
running it against the live stack; **all 213 tests had passed.**

### Penalty
None. This slide has no penalty — it is evidence collection. Worth saying
explicitly.

### Image
`fig_offerlog.png` — NEW. One log row as a table: Ujjwal 695 m / −750 friend
bonus / score −55 / rank 1; stranger 31 m / 0 / 31 / rank 2. Caption: *without
the bonus Ujjwal scores 695 and loses. The app caused that pairing.*

---

## Slide 5 — Deliberate Exploration

**Title:** Buying back observability with 5% of offers

### The gap
[10] Perdomo et al. establish that a deployed model changes the distribution it
predicts. The standard remedy in recommendation is **exploration** — collecting
some data under a policy you did not optimise. It has never been proposed as a
mechanism for **preserving fraud observability**.

### What we built
With probability ε (default **5%**) a dispatch round is ranked on distance alone
— social term removed **and** hop ceiling lifted.

Both must go together: removing the boost while still hiding the errand from
strangers leaves the sample exactly as biased, because the strangers whose
absence is the problem still get offered nothing.

### Verified
- **[LIVE]** The flip works on the real stack. Friend at 695 m, stranger at 31 m:

| Round | Friend's score | Stranger's score | Offered first |
|---|---|---|---|
| Normal | **−53.6** | 31.0 | **friend** |
| Exploring | **694.6** | 31.0 | **stranger** |

- **[SIM]** At the deployed setting: ε=0% → ring **missed** (z 2.3);
  ε=5% → **caught** (z 3.8); ε=10% → z 4.5. Honest groups stay clear throughout.
- **[TEST]** ε=0.0 is an exact kill switch — 500 draws, never explores
- **[TEST]** Rate read per call, so it changes without a deploy

### The cost, stated honestly
1 errand in 20 gets a worse-matched runner. That is the price of being able to
detect collusion at all. It is a configuration value, not a redesign.

### Penalty
None directly. It changes what data exists, not what happens to anyone.

### Image
`fig_matching.png` — EXISTING. The branch diagram, 95% / 5%.

---

## Slide 6 — The z Check

**Title:** Using our own matcher as the null hypothesis

### The gap
Ring thresholds in the literature and in our own first version — group size, leg
value, laps, concentration — are **hand-tuned constants**. There is no test
statistic, therefore no principled false-positive rate. You cannot state how
often you are wrong.

### What we built
The matcher already knows how likely each candidate was to take each errand.
Sum that across a group's rounds and you have what the policy **expected**.
Compare against what **happened**:

```
excess = observed in-group takes − expected in-group takes
z      = excess / natural variation
```

Worked example, 200 errands:

| | Rounds | Expected | Group A took | Group B took |
|---|---|---|---|---|
| Normal | 190 | 178.6 | 177 | 190 |
| Exploring | 10 | 3.0 | 3 | 10 |
| **Total** | **200** | **181.6** | **180** | **200** |

| | Expected | Observed | Gap | z | Verdict |
|---|---|---|---|---|---|
| A (honest) | 181.6 | 180 | −1.6 | −0.4 | **explained — no flag** |
| B (ring) | 181.6 | 200 | +18.4 | **5.1** | unexplained — continue |

Same expectation for both, because the matcher treats them identically. Only
behaviour differs.

**Ten exploring rounds contribute ~40% of the ring's evidence** — roughly 13×
what a normal round is worth. That is why 5% is enough.

### Verified
- **[SIM]** Naive flags 6/6 honest; excess flags **0/6** and still finds the ring
- **[SIM]** Co-located stress test: ring at the same desk still caught at 85%
  loyalty (z 3.7). It hides only by **restraint** — which rate-limits how much it
  can farm
- **[TEST]** Below 25 rounds it returns nothing and the detector behaves exactly
  as before — silence is not a verdict
- **[TEST]** Exculpatory only: low z suppresses a flag, high z never raises
  severity or manufactures one

### Penalty
It **removes** penalties rather than adding them. Its whole job is to stop
innocent groups being flagged.

### Image
`fig_pipeline.png` — EXISTING. The full flow, with the z gate in the middle.

---

## Slide 7 — LLM Corroboration

**Title:** The one question arithmetic cannot answer

### The gap
Three roommates genuinely taking turns fetching dinner produce the **identical
triangle** and **identical circulation** as three students farming. The graphs
are mathematically the same shape. Structure answers *who* and *how much*.
Neither can answer ***what for***.

LLM fraud work (e.g. Ergun, ISAF 2025) applies models to detection but does not
constrain them to an advisory, exculpatory-only role over attacker-written text.

### What we built
Local `qwen2.5:7b` via Ollama — no per-call cost, no user data leaving campus.
Asked one question about a group that **already failed** the money check and the
z check: *do these errands read as genuine campus life?*

Reads from PostgreSQL, not the graph: errand titles, vendors, times, notes,
items — and only errands **within** the group.

Three non-negotiable rules:
1. **Advisory only.** Never punishes, never withholds, never raises a severity.
   Its useful direction is **exculpatory** — clearing honest groups, where being
   wrong is cheapest.
2. **The text is written by the accused.** Fenced, labelled untrusted,
   schema-constrained. The worst a crafted note can do is move a number an admin
   can overrule. It can never become an instruction.
3. **Silence is neither innocence nor guilt.** Model down → returns nothing →
   everything behaves as before.

### Verified
- **[LIVE]** On the seeded ring: `reads_as_genuine: false`, coherence 0.35,
  diversity 0.45, with its own observations — *"Near-identical titles and
  intervals"*, *"Single vendor used for stationery"*
- **[LIVE]** Scores are 0–100 integers, not 0.0–1.0, because a 7B model asked
  for decimals was **measured** returning `4.0` on a five-point scale it
  invented, which Pydantic then rejected — silently killing the channel
- The review channel for ratings is **switched off** (`review_analysis_enabled =
  False`): measured not to discriminate. An advisory that clears fraudsters who
  write well while failing honest runners whose friends write nothing is worse
  than none.

### Penalty
**Zero.** It creates no flags — `semantics.py` never constructs a `FraudFlag`.
Its output is merged into the `details` of a flag that already exists.

### Image
`fig_llm.png` — NEW. Left: two identical triangles (roommates vs ring) with
"structure cannot tell these apart". Right: the two errand lists side by side —
varied vs template. Bottom: the actual JSON verdict.

---

## Slide 8 — How Penalisation Actually Works

**Title:** Five consequences, none of them a ban

### The point
No detector punishes on its own authority. An unreviewed flag can demote a
runner; it can never remove them.

| # | Mechanism | Stored in | Takes effect |
|---|---|---|---|
| 1 | Reputation deflation | `users.effective_reputation` | Matching score, automatic |
| 2 | Flag penalty | `fraud_flags` | +300 / +700 / +1200 m, capped at 2000, decays |
| 3 | Co-ring exclusion | flag `details.members` | Candidate removed before ranking |
| 4 | Escrow withholding | `escrow_holds` → PENDING_REVIEW | Wallet, price flags only |
| 5 | Strike ladder | `user_strikes` | warn → −0.5 → 7-day block → account |

### Points to land
- Severity is **hardcoded per rule**, never model-decided — 3 for rings, 2 for
  farming, arithmetic for price. If severity responded to the model, an attacker
  could tune their errand titles to move their own penalty.
- A severity-3 penalty (**1200 m**) is deliberately **less** than the friend
  boost (1500 m). Suspicion demotes; it cannot exclude.
- Strike level 1 needs **three separate flagged errands** — a pattern, not an
  accident.
- **Idempotent by construction:** the level is a function of the flag count, and
  a strike is written only when that level exceeds strikes already on file.
  Re-running can never double-punish.
- Dismissal is **one word** — status OPEN → DISMISSED — and all three automatic
  effects stop at once, because each only matches OPEN or UPHELD.

### Image
`fig_penalty.png` — NEW. One flag row in the centre; five arrows out to the five
consequences, each labelled with where it is stored and where it lands.

---

## Summary of what I need to build

| Figure | Status |
|---|---|
| `fig_social.png` | exists |
| `fig_matching.png` | exists |
| `fig_pipeline.png` | exists |
| `fig_farming.png` | **new** — Karan vs Meera, discount curve |
| `fig_flaw.png` | **new** — the collision + saturation chart |
| `fig_offerlog.png` | **new** — one log row, annotated |
| `fig_llm.png` | **new** — identical graphs, different text |
| `fig_penalty.png` | **new** — one row, five consequences |

**Suite status for the closing slide: 234 tests passing.**

---

## Before I build — three things to confirm

1. **Order.** I've put rings before exploration/z, because the problem must come
   before the solution. Keep, or revert to your order?

2. **Slide count.** Eight. I added the flaw slide (3) and the penalty slide (8)
   to your five. Both feel necessary — 3 is where your contribution actually
   lives, and 8 is the "so what happens to them" question that always gets
   asked. Drop either?

3. **Rating farming.** Your earlier split gave price integrity to Ujjwal and
   rating farming was listed under my three detectors. Confirm farming is yours
   and not his, so the two of you don't present the same slide.
