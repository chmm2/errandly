# Sanskriti — slide plan for Review 2

Ten slides. Same shape on every one, because that is what the panel is marking:

> **the gap in prior work  →  what we built  →  proof it works  →  what it changes**

Every "verified" line is something actually measured, tagged:

- **[LIVE]** — measured on the running stack (real Neo4j, Redis, Postgres)
- **[TEST]** — enforced by an automated test in the suite
- **[CONST]** — computed directly from the constants the deployed system uses

---

## The one-sentence claim

Everything on these slides supports one thing, and it should be said in these
words:

> **Trust decays with the AGE of the newest link on the path, not only with
> distance.**

Not "we used a graph" — the graph traversal and hop decay are applied work from
Jiang et al. The **time dimension** is the contribution. If that sentence lands,
the slides have done their job.

---

## Slide 1 — Title

**Trust-Aware Social Matching**
*How Errandly decides who is offered an errand, and why a new friendship is
worth less than an old one*

Sanskriti Sajlal · 23BCE0832

---

## Slide 2 — What this half covers

One table, no prose.

| # | Mechanism | The gap it answers |
|---|---|---|
| 1 | Friendship graph, projected and rebuildable | Trust-aware allocation [3] has no peer graph at all |
| 2 | Trust over paths up to 4 hops | [1] formalises decay, applied here |
| 3 | **Maturity — decay by edge age** | **[1] decays by distance only. Nobody models time.** |
| 4 | Tiered offering — 2 hops for 45 s | [2] stops at rating weight; the graph never reaches assignment |
| 5 | Closure penalty on a sealed neighbourhood | Structure alone cannot separate a friend group from a ring |

**Line to say:** *"Three of these are applied work. Row 3 is the contribution."*

Being explicit about which parts are applied is worth more than claiming all of
it — a panel trusts a student who draws that line themselves.

---

## Slide 3 — The problem

Three short points, no citations yet.

- A market between strangers. Money moves before the service is rendered, and
  quality is observed only by the two people involved.
- **But trust on a campus is not uniform.** Students already know some of their
  neighbours, and an errand run by an acquaintance carries materially less risk
  than one run by a stranger.
- That existing structure is free information — **if** you can represent it,
  measure it, and stop it being gamed.

**Closing line:** *"This layer is responsible for all three."*

### Image
None. This slide is 30 seconds of setup.

---

## Slide 4 — What the three papers do

The literature table, in the Review-1 format.

| Paper | What it establishes | What it leaves open |
|---|---|---|
| **[1] Jiang et al.**, ACM Computing Surveys, 2016 | Trust must **decay along a path** — a friend-of-a-friend-of-a-friend cannot count as much as a direct friend. The rate of decay is a design parameter. | Decay is a function of **distance alone**. An edge is an edge — a friendship from three years ago and one from this morning contribute identically. |
| **[2] Chiou & Tu**, IEEE Access, 2020 | A rating from someone close to you is worth more than one from a stranger. Implemented with cryptographic rater privacy on Android. | Stops at **rating weight**. The social graph never reaches the assignment decision itself. |
| **[3] Fu & Liu**, The Computer Journal, 2021 | Trust as a **formal objective** in task allocation, not an afterthought. Beats cost-optimal assignment on completion reliability. | Trust comes only from **platform history**. No peer graph, so a new user is indistinguishable from any other new user. |

**Closing line — this is the slide's whole job:**

> *"All three agree trust should inform assignment. None of them models TIME. A
> relationship either exists or it does not, and if it exists it counts in full
> from the instant it is created."*

---

## Slide 5 — The gap, and why it matters here

### The gap
On a campus, **creating a friendship is free and instant.** A request, an
accept, and an edge exists. If that edge immediately confers full trust, the
entire social layer can be acquired in an afternoon.

### Two forms of the attack
- **Targeted** — find a student who posts many errands, befriend them, collect a
  1500 m head start on everything they post from that moment.
- **Breadth** — the reputation layer weights ratings by *distinct rater*, so
  repeating a rating is worthless. The cheapest remaining evasion is to recruit
  eighty friends and have each rate once, which scores exactly as a genuinely
  popular runner does.

### Why the second matters most
It is where the rest of the fraud work **pushes** an attacker. Every one of
those eighty ties has to be created, and created recently.

> *"If new edges carry full weight, the defence has only moved the attack rather
> than stopped it."*

### Image
None, or a simple two-box diagram: *befriend today → full trust today*.

---

## Slide 6 — What we built

### The formula
```
trust  =  0.45 ^ (hops − 1)   ×   (1 − penalty)   ×   maturity
```

Three factors, three questions:

| Factor | Question |
|---|---|
| `0.45 ^ (hops − 1)` | How far away are they? |
| `1 − penalty` | Is this group sealed off? |
| **`maturity`** | **How new is the newest link on the path?** |

### The graph itself
- Accepted friendships projected from PostgreSQL into Neo4j, **each stamped with
  the date it was accepted**
- A **derived** read model — nothing is authoritative there, and it can be
  rebuilt from PostgreSQL at any time
- Every read **degrades to a neutral value** if the graph is unavailable, so an
  outage makes matching less socially targeted rather than stopping it

### Verified
- **[LIVE]** Full rebuild from PostgreSQL: 326 users, 14 friendships, 215
  settlements projected, metrics recomputed

### Image
`fig_trust_flow.png` — exists. Graph → shortest path → newest edge →
neighbourhood → the formula → matching.

---

## Slide 7 — Matching depth

### The hop table — [CONST], straight from deployed values

| Relationship | Hops | Trust | Head start |
|---|---|---|---|
| Direct friend | 1 | 1.0000 | **1500 m** |
| Friend of a friend | 2 | 0.4500 | 675 m |
| Three hops | 3 | 0.2025 | 304 m |
| Four hops | 4 | 0.0911 | 137 m |
| Stranger | — | 0 | 0 m |

**Why 0.45:** a friend-of-a-friend should be clearly better than a stranger and
clearly worse than a friend. At four hops the contribution is ~9% — enough to
order candidates, not enough to let distant connections dominate.

**Why stop at 4:** beyond four hops a path exists but means nothing in practice.

### The subtlety worth presenting — §4.4 of the document
**Sorting by trust does not, on its own, give a friend the errand.** Every
candidate is published to within milliseconds of the others and the first to
accept wins. In that race the nearest stranger usually taps first, whatever the
sort order said.

So an errand is **withheld** from anyone beyond two hops for the first
45 seconds. **That withholding, not the sort, is what confers first refusal.**
The tier then widens on a timer, and falls straight through to an open offer if
nobody connected is nearby — an errand nobody sees is worse than one a stranger
takes.

This is a good beat: it is a finding that only appears once you build the thing.

### Image
Right half of `fig_trust_curves.png` — the bar chart by hop distance.

---

## Slide 8 — Friendship decay  ★ the contribution

### The ramp — [CONST]

| Age of the newest edge | Weight |
|---|---|
| 0 days | **0.40** |
| 7 days | 0.54 |
| 15 days | 0.70 |
| 30 days and after | 1.00 |

### Three properties, all deliberate

**It is the NEWEST edge on the path, not the average.** A chain of trust is only
as established as its most recently created link. A two-year friendship reached
through an edge made yesterday tells you about yesterday.

**There is a floor, not a zero.** Most new friendships are exactly what they
appear to be. A new tie is discounted, never treated as worthless — the ordinary
case must not be punished to inconvenience the rare one.

**Old edges are NOT decayed.** Age makes a friendship *stronger* evidence, not
weaker: a tie that has survived two years is more likely real than one from last
week. Decaying it would penalise the entire ordinary population while costing an
attacker nothing, since rebuilding a stale network is free.

*(An unknown edge date counts in full — edges written before the date field
existed are genuinely old, and treating missing data as suspicious would
penalise the platform's earliest users for the platform's own gap.)*

### What it costs an attacker — [CONST]

| | Trust | Head start |
|---|---|---|
| Befriend a heavy requester **today** | 0.4200 | **630 m** |
| The same friendship after a month | 1.0000 | 1500 m |
| Two hops, newest link **one day old** | **0.1890** | 284 m |

That last row is worth explaining out loud: hop decay (0.45) and maturity (0.42)
**multiply**. Freshness and distance compound rather than trading off.

### Verified
- **[TEST]** Six dedicated tests, including
  `test_recruiting_a_network_today_does_not_pay_off_today` and
  `test_age_never_reduces_trust`
- **[CONST]** Every number above computed from the deployed constants

### Image
Left half of `fig_trust_curves.png` — the maturity ramp.

---

## Slide 9 — On the running system

### The measurement — [LIVE]
Executed against the live stack: real Neo4j, real Redis geospatial index, real
dispatch path.

Chris as requester. Ujjwal a direct friend, placed **695 m** away. An
unconnected student placed **31 m** away.

```
graph:  friend    hops = 1     trust = 0.499
graph:  stranger  hops = none  trust = 0.000

rank 0   FRIEND     695 m   score  −53.6      <- offered first
rank 1   stranger    31 m   score   31.0
```

**Line to say:**

> *"The friend is more than twenty times further away and still ranks first,
> because half a friendship is worth roughly 750 metres of walking."*

### Also worth stating
That same behaviour is what the collusion work later had to account for — the
matcher pushing friends together is exactly what biases the fraud evidence. Say
it yourself; it hands the panel the link between your half and Chris's, and it
shows the two of you understand each other's work.

### Image
None needed — the code block is the evidence.

---

## Slide 10 — Design decisions, and limits

### Two decisions worth defending

**Closure, not the clustering coefficient.** Clustering divides by
degree × (degree − 1), so a small clique cannot score high however closed it is —
a four-person ring scores ~0.5 while a ten-person hostel block scores 0.8. That
ranks the threat **exactly backwards**, since the small ring is the likelier
collusion unit. Closure — internal edges over internal plus boundary — is
size-independent.

**Structure alone never discounts a direct friend.** A close-knit friend group
is the most ordinary thing on a campus and the strongest honest trust signal the
platform has. Only money-flow evidence justifies a discount on a direct
friendship — the conjunction, never either half alone.

### Limitations, stated first

- **The constants are unfitted.** No live data supports 30 days, 0.40 or 0.45
  specifically. They are defensible choices, not measured optima.
- **Maturity delays an attack, it does not prevent one.** An attacker patient
  enough to build a network a month in advance pays no penalty. It raises the
  cost and the planning horizon.
- **Trust is symmetric.** Friendship is an undirected edge. In reality A may
  rely on B more than B relies on A, and the model cannot express that.
- **The graph can drift.** It is rebuildable, but nothing detects divergence
  automatically — the rebuild is run deliberately.

Stating these yourself is worth more than being asked. It also sets up
Project-II.

---

## Summary of images needed

| Figure | Status |
|---|---|
| `fig_trust_flow.png` | **exists** — how one trust score is assembled |
| `fig_trust_curves.png` | **exists** — maturity ramp + hop decay, two panels |
| A simple attack diagram for slide 5 | optional, probably skip |

Both existing figures were generated from her own deployed constants, so they
cannot drift from the code.

---

## Anticipated questions — put these in her notes, not on a slide

| Question | Answer |
|---|---|
| Why not just use distance? | Distance predicts who *can* get there, not who *will deliver properly*. On a closed campus the social graph is free information about the second question, and [1]–[3] establish it improves outcomes. |
| Why 30 days and 0.40? | They bound the attack rather than model friendship. 0.40 is low enough that a same-day edge cannot outrank a genuinely near stranger; 30 days is longer than any plausible farming sprint. Stated as unfitted constants. |
| Why not decay OLD friendships too? | Age is evidence of authenticity, not staleness. Decaying it punishes the ordinary population while costing an attacker nothing — rebuilding a stale network is free. |
| Why the newest edge, not the average? | A chain is only as established as its most recent link. Averaging would let one old friendship launder a brand-new one. |
| Isn't this unfair to new students? | It would be if it were absolute. The tier widens on a timer and falls straight through when nobody connected is nearby — a student with no friends waits 45 seconds, not forever. |
| What if the graph goes down? | Every read degrades to neutral and matching falls back to distance ordering. Unavailability is never read as evidence against anyone. |
| Is this novel or just applied? | The traversal and hop decay are applied [1]. **The novelty is the time dimension** — decaying trust by the age of the newest edge, which none of the three approaches models. |

---

## Before building the deck — three things to check

1. **Does Sanskriti agree the closure penalty is hers?** It sits in her module,
   but it consumes the circulation figure from Chris's. Suggested split: the
   closure structure is hers, the circulation input is his. Say it that way on
   slide 10 and neither of you is claiming the other's work.

2. **Slide count — ten.** Slide 3 (the problem) and slide 5 (the gap) could
   merge if she wants eight. I would keep them separate: the gap slide is where
   her contribution is justified, and it deserves its own screen.

3. **Does she want the live measurement on slide 9?** It is the strongest
   evidence she has, but it is Chris's test run. Either re-run it under her name
   or present it as a joint verification — just do not leave it ambiguous.
