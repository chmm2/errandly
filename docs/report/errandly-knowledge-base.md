# Errandly — consolidated knowledge base

Everything needed to generate a combined Review-2 deck, assembled from the three
individual decks. Written to be pasted into a fresh chat as context.

**Nothing in this file is invented.** Every number is either measured on the
running system, produced by a stated simulation, or read from the deployed
constants. Tags used throughout:

- **[LIVE]** — measured on the running stack (real Neo4j, Redis, PostgreSQL)
- **[SIM]** — simulation; parameters always stated alongside
- **[TEST]** — enforced by an automated test in the suite
- **[CONST]** — computed directly from constants the deployed system uses

---

## 1. Project identity

| | |
|---|---|
| **Title** | Errandly: A Trust-Aware, Fraud-Resistant Platform for Campus Errands, Micro-Delivery and Commerce |
| **Course** | BCSE497J Project-I · Review 2 |
| **Institution** | School of Computer Science and Engineering, Vellore Institute of Technology, Vellore |
| **Guide** | Dr. Ranjithkumar S, Assistant Professor, SCOPE |
| **Project ID** | 20226UG03 |
| **Date** | September 2026 |

**Team** (sorted on register number):

| Register no. | Name | Owns |
|---|---|---|
| 23BCE0743 | Chris Martin Mattam | Collusion rings, offer log, exploration, rating farming, LLM corroboration |
| 23BCE0832 | Sanskriti Sajlal | Trust-aware matching, friendship graph, decay |
| 23BDS0335 | Ujjwal Gogoi | Escrow wallet, price list, headroom, settlement |

---

## 2. The project in one page

**Aim.** To design, develop and validate Errandly — a campus-verified platform
on which VIT students earn through paid peer-run errands and resell pre-owned
essentials inside a closed, trust-verified network, with every transaction
settled through an escrow wallet — so that campus errands and resale happen
safely, without informal cash deals or outside gig-platform markups.

**Four pillars:**

- **Verified, not open** — only campus-email-verified students can post or accept
- **Escrow, not trust-me** — payment is held by the app, released on confirmed delivery
- **Commerce, not just delivery** — a peer resale marketplace on the same rails
- **Trusted, and still checkable** — routing uses who you know, without blinding
  the platform's own fraud detection

**The real-world problem.** Food-delivery apps take **21–24%** of every order
with a flat platform fee on top. **Zero** campus platforms verify both sides of a
peer transaction before money moves. Every semester usable furniture, cycles and
books are discarded for want of a resale channel.

**Stack.** FastAPI modular monolith · PostgreSQL + PostGIS · Redis (GEO, locks,
pub/sub) · Kafka (transactional outbox → relay → consumer groups) · MongoDB
(chat) · Neo4j (derived social graph) · Ollama running `qwen2.5:7b` locally ·
React Native / Expo mobile · React + Vite web.

**Current status:** **260 automated tests passing** on the merged branch. *(The
individual decks quote 225 and 234 — those were taken before the branches were
merged. Use 260 in any combined deck.)*

---

## 3. How the three halves connect

The dependency runs in one direction, and stating it is worth a slide of its own:

```
Sanskriti — decides WHO is offered the errand
        ↓
Ujjwal    — holds the money and decides whether the reported price is honest
        ↓
Chris     — reads the history the other two produce, and looks for collusion
        ↑
        └── and finds that Sanskriti's layer biases the evidence his layer needs
```

**The line to say:** *the research finding only exists because all three were
built.* Without the trust layer the flaw never appears; without the collusion
layer nobody notices it.

---

## 4. Ujjwal Gogoi — escrow for a price nobody knows yet

### 4.1 The problem
Money must be taken from the customer **before anyone knows what the order will
cost**.

- Wait until delivery and the customer may have spent it — the runner has already
  paid cash at the shop and is out of pocket. **So locking at order time is not
  negotiable.**
- But at order time nobody knows the bill. A puff is ₹23 at one canteen and ₹30
  at another, and prices move.
- **Lock too little** → the runner cannot be repaid.
  **Lock an open-ended amount** → the customer has handed over a blank cheque.

Both failures are unacceptable and they pull in opposite directions.

*(Terminology to define early: **MRP** is the price printed on a packet, fixed by
law. **Non-MRP** is anything without a printed price — a puff, a tea, loose
vegetables.)*

### 4.2 Prior work, in two families

**Family A — holding money safely**

| Work | What it establishes |
|---|---|
| Gray & Reuter, 1993 | A payment either fully happens or does not happen at all. No half-payments, even if a server dies. |
| Sagas (Garcia-Molina & Salem), 1987 | A long job split into small steps, each with an undo step for when a later step fails. |
| Helland, 2007 | How to stay correct when a payment crosses separate systems that cannot lock each other. |
| Escrow schemes | Hold money in the middle until the job is done, so neither side trusts first. |
| Card pre-authorisation | A hotel or fuel pump freezes a set amount, then charges the real amount later. |

**What they all assume:** the amount being locked is **already known and fixed**
when you lock it. A hotel picks the deposit. A fuel pump freezes a set figure.
Somebody always knows the number in advance.

**Family B — working out what things should cost**

| Work | What it establishes |
|---|---|
| Li et al., 2016 (truth discovery) | When many people report different values, infer both the real value and who is reliable. |
| Rousseeuw & Croux, 1993 | Use the middle value, not the mean, so extremes cannot drag the answer. |
| Gelman & Hill, 2007 | Judge a shop with two recorded prices mostly by campus norms; one with twenty on its own record. |
| Nigeria crowdsourced food prices, 2023 | Volunteer price reports matched trained surveyors closely once cleaned. |
| Sarpal et al., 2023 | Flag a listing whose price looks wrong against similar products and past prices. |

**What they all assume:** the price question is settled **after the fact**. It is
an analysis problem, not a payment problem.

### 4.3 The gap
> **One field locks money but needs the amount in advance. The other works out
> the amount, but only afterwards. Nobody uses a maintained price list to decide
> how much to lock.**

Two things must hold at once that normally conflict:

- The runner must **always be repayable**, whatever the shop charges on the day
- The customer must **never face an open-ended charge** — a hard ceiling they agreed to

### 4.4 Why each specific paper does not cover it

| Research | What it assumes | Why that breaks here |
|---|---|---|
| Gray, Sagas, Helland | The amount is known when the payment starts | Ours is discovered at the shop counter, hours later |
| Escrow schemes | Both sides agree a fixed sum up front | Nobody can name the sum — the shop has not been visited |
| Card pre-authorisation | The business picks a fixed holding amount | **Closest match**, but the amount is arbitrary and the spender is a peer, not the business |
| Li 2016, Sarpal 2023 | The price is worked out afterwards, for analysis | We need the number *before* the money moves |
| Rousseeuw 1993 | The goal is an accurate single figure | We need a figure **and a safe margin around it** |
| Gelman 2007 | A tool for judging shops with little data | Useful, but it never had to fund a payment |

### 4.5 The answer

**Part 1 — lock at order time.** The moment an order is placed the money leaves
the spendable balance and sits in escrow. Not at delivery, not when a runner
accepts. **An unfunded order is refused at the point of posting**, so by the time
a runner is at a counter with their own cash, the money to repay them already
exists and is reserved.

The customer sees two numbers: **spendable** and **locked**.

**Part 2 — headroom, only where the price can move.** Loose-priced (non-MRP)
items get **+16%**. A printed MRP cannot change, and cash named for a gate pickup
is exact — padding those would lock money no outcome could need.

### 4.6 What the two decisions buy

- **Everyone is solvent at the end** — the repayment was reserved before a rupee was spent
- **The customer's exposure has a hard ceiling** — estimate + 16%, and never more
- **Loose prices move freely inside the band** — ₹23 → ₹26 settles normally, nobody flagged
- **Anything unused returns** — the 16% is a reservation, not a fee

### 4.7 The ceiling is where a human takes over
If the runner spends past the ceiling, the system does **not** quietly pay it and
does **not** quietly refuse it.

- Paying it charges the customer money they never agreed to
- Refusing it makes the runner absorb a possibly genuine price rise

Neither is the system's to decide, so **nothing moves**. The order freezes and an
admin looks. The customer's money stays locked — visibly still theirs, not
refunded and then clawed back.

### 4.8 Verified
- **[LIVE]** Wallet with two partitions, escrow at order time, 16% band on
  non-MRP lines only
- **[LIVE]** Price list with type-ahead search, so a customer picks a known item
  rather than typing free text
- **[LIVE]** The runner must report what they paid, per item, **before** they can
  mark the order picked up
- **[LIVE]** Settlement pays the runner, returns the surplus, freezes anything
  past the ceiling
- **[TEST]** Money logic covered, including the worked examples on the slides
- Mobile and web, against the same backend

### 4.9 His prepared answers
| Question | Answer |
|---|---|
| *"This is just card pre-authorisation."* | Closest existing thing, and we say so. The difference: a hotel picks its own deposit figure; ours is worked out **per item from a maintained price list**, and only unknown-price items are padded at all. |
| *"Why 16%?"* | Honest answer: a chosen figure that covers normal campus price movement without locking too much. **It should be derived from the recorded spread per item — that is the obvious next piece of work.** |
| *"What if a price rises more than 16%?"* | The order freezes, an admin decides, and the price list gets updated. |
| *"Why not take the money at delivery?"* | Because the runner has already paid cash by then. If the wallet is empty, they lose their own money. |

---

## 5. Sanskriti Sajlal — trust-aware social matching

### 5.1 The one-sentence claim
> **Trust decays with the AGE of the newest link on the path, not only with
> distance.**

The graph traversal and hop decay are **applied work**. The time dimension is the
contribution. Say which is which — it is worth more than claiming all of it.

### 5.2 Scope

| # | Mechanism | The gap it answers |
|---|---|---|
| 1 | Friendship graph, projected and rebuildable | [3] scores trust from platform history only — no peer graph at all |
| 2 | Trust over paths up to 4 hops | [1] formalises path decay. **Applied.** |
| 3 | **Maturity — decay by edge age** | **[1] decays by distance only. None of the three models time.** |
| 4 | Tiered offering — 2 hops for 45 s | [2] folds the graph into rating weight; it never reaches assignment |
| 5 | Closure penalty on a sealed neighbourhood | Structure alone cannot separate a friend group from a ring |

### 5.3 Prior work

| Paper | What it establishes | What it leaves open |
|---|---|---|
| **[1] Jiang et al.**, ACM Computing Surveys, 2016 | Trust must **decay along a path**; the rate is a design parameter | Decay is a function of **distance alone**. An edge is an edge — three years old and this morning contribute identically |
| **[2] Chiou & Tu**, IEEE Access, 2020 | A rating from someone close to you is worth more; cryptographic rater privacy | Stops at **rating weight**. The graph never reaches the assignment decision |
| **[3] Fu & Liu**, The Computer Journal, 2021 | Trust as a **formal objective** in allocation; beats cost-optimal on reliability | Trust from **platform history only**. No peer graph, so a new user is indistinguishable from any other |

**Closing line:** *All three agree trust should inform assignment. None models
TIME — a relationship either exists or it does not, and if it exists it counts in
full from the instant it is created.*

### 5.4 The gap
Creating a friendship is **free and instant**. If a fresh edge confers full
trust, the whole social layer can be bought in an afternoon.

- **Targeted** — befriend a heavy requester, collect a 1500 m head start on
  everything they post from that moment
- **Breadth** — ratings are weighted by *distinct rater*, so repeating is
  worthless. The cheapest remaining evasion is to recruit eighty friends and have
  each rate once — which scores exactly as a genuinely popular runner does

The second matters most: it is **where the rest of the fraud work pushes an
attacker**, and every one of those ties has to be created recently.

### 5.5 The formula
```
trust = 0.45^(hops−1)  ×  (1 − closure penalty)  ×  maturity
```

| Factor | Question it answers |
|---|---|
| `0.45^(hops−1)` | How far away are they? |
| `1 − closure penalty` | Is this group sealed **and** circulating money? |
| **`maturity`** | **How new is the newest link on the path?** |

### 5.6 Matching depth — [CONST]

| Relationship | Hops | Trust | Head start |
|---|---|---|---|
| Direct friend | 1 | 1.0000 | 1500 m |
| Friend of a friend | 2 | 0.4500 | 675 m |
| Three hops | 3 | 0.2025 | 304 m |
| Four hops | 4 | 0.0911 | 137 m |
| Stranger | — | 0 | 0 m |

Past four hops a path exists but means nothing — treated as strangers.

**The subtlety worth presenting:** sorting by trust does **not** on its own give
a friend the errand. Every candidate is published to within milliseconds and the
first to accept wins; the nearest stranger usually taps first. **Withholding the
offer beyond two hops for 45 seconds is what confers first refusal.** The tier
widens on a timer, and falls straight through when nobody connected is nearby.

### 5.7 Friendship decay — the contribution — [CONST]

| Age of the newest edge | Weight |
|---|---|
| 0 days | 0.40 |
| 7 days | 0.54 |
| 15 days | 0.70 |
| 30 days + | 1.00 |

**Three deliberate properties:**

1. **The NEWEST edge, not the average.** A chain of trust is only as established
   as its most recently created link. A two-year friendship reached through an
   edge made yesterday tells you about yesterday. Averaging would let one old
   friendship launder a brand-new one.
2. **A floor of 0.40, not a zero.** Most new friendships are exactly what they
   look like. The ordinary case must not be punished to inconvenience the rare one.
3. **Old edges are NOT decayed.** Age makes a friendship *stronger* evidence. A
   tie that survived two years is more likely real. Decaying it would punish the
   whole ordinary population while costing an attacker nothing — rebuilding a
   stale network is free.

*(An unknown edge date counts in full: edges predating the field are genuinely
old, and treating missing data as suspicious would penalise the platform's
earliest users for the platform's own gap.)*

**What the attack costs — [CONST]**

| | Trust | Head start |
|---|---|---|
| Direct friend, established | 1.0000 | 1500 m |
| **Direct friend, made today** | **0.4200** | **630 m** |
| Two hops, newest link one day old | **0.1890** | 284 m |

That last row: hop decay (0.45) and maturity (0.42) **multiply**. Freshness and
distance compound rather than trading off.

### 5.8 The closure penalty
A discount from 0 to 0.95, applied **only where both hold**: the neighbourhood is
sealed **and** money circulates inside it.

| Direct friend's group | Penalty | Trust |
|---|---|---|
| Normal | 0 | 1.00 |
| **Sealed, money flows outward** | **0** | **1.00** |
| Sealed **and** money circles inside | 0.59 | 0.41 |

Rows 1 and 2 identical is deliberate: **structure alone never discounts a direct
friend.** A close-knit friend group is the most ordinary thing on a campus and
the strongest honest trust signal the platform has.

**Why it exists:** without it the matcher hands ring members each other's errands
at full trust — *actively feeding the thing the platform is trying to detect*.

*(Boundary note: `closure` is Sanskriti's, computed from the friendship graph.
`circulation` comes from Chris's module. This one term is where the two halves
meet — say so rather than let a panel notice the shared import.)*

### 5.9 Verified
- **[TEST]** Six dedicated tests, including
  `test_recruiting_a_network_today_does_not_pay_off_today` and
  `test_age_never_reduces_trust`
- **[LIVE]** Graph rebuild from PostgreSQL: 326 users, 14 friendships, 215
  settlements projected
- **[CONST]** Every trust figure above computed from deployed constants

### 5.10 Design decisions
**Closure, not the clustering coefficient.** Clustering divides by
degree × (degree − 1), so a four-person ring scores ~0.5 while a ten-person
hostel block scores 0.8 — **ranking the threat exactly backwards**, since the
small ring is the likelier collusion unit. Closure is size-independent.

### 5.11 Limitations
- Constants are **unfitted** — no live data supports 30 days, 0.40 or 0.45
- **Maturity delays an attack, it does not prevent one** — a patient attacker who
  builds a network a month ahead pays nothing
- **Trust is symmetric** — an undirected edge cannot express A relying on B more
  than B relies on A
- **The graph can drift** — rebuildable, but nothing detects divergence automatically

---

## 6. Chris Martin Mattam — collusion rings and policy-conditioned evidence

### 6.1 Scope

| # | Mechanism | The gap it answers | Consequence |
|---|---|---|---|
| 1 | Rating farming detection | EigenTrust admits collusive groups defeat it, unsolved | Reputation discounted + 700 m |
| 2 | Collusion ring detection | Graph defences assume the graph is observed, not produced | 1200 m + removed from each other's errands |
| 3 | The offer log | Marketplace fraud work is retrospective; nothing records *why* a match was made | None — evidence collection |
| 4 | Deliberate exploration | Exploration is standard for unbiased evaluation, never for fraud observability | None — changes what data exists |
| 5 | LLM corroboration | Structure and money answer who and how much, never *what for* | None — advisory only |

**Only the first two can penalise anyone.** The other three exist so the first
two accuse the right people.

### 6.2 Rating farming

**The gap.** Kamvar et al. (EigenTrust, WWW 2003) is the canonical reputation
algorithm and **its own authors state it is defeated by groups who rate each
other up** — named, not solved. Chiou & Tu weight a rating by closeness, and
closeness only ever **raises** weight — reasonable for the honest case, backwards
for the adversarial one.

**What was built — two layers.**

*Always on, no flag:*
- **One rater, one vote** — ten ratings from one friend count as one opinion
- **Friend ratings discounted** as concentration rises: 1.00 at 50%, **0.25 at 100%**
- **Confidence shrinkage** — a thin profile is pulled toward neutral 3.5

*The flag:* two gates (4+ friend ratings, 70%+ concentration), then any of three
questions:
1. Do friends rate them much higher than strangers? *(gap ≥ 0.8 stars)*
2. Did friends rush to rate them right after a penalty? *(2+ within 14 days)*
3. Has any stranger ever rated them at all? *(15+ friend, ≤1 stranger)*

**Verified — [LIVE]**
- Ten fake five-star ratings from one friend moved a runner from **3.50 to 3.55**
- Before one-rater-one-vote: **100 farmed ratings scored 4.64 against 4.57 for 20
  honest stranger ratings** — patience beat the discount. Counting people removed
  it at the root.

**Confidence shrinkage — everyone below has a perfect 5.0 average:**

| Effective votes | Score they get |
|---|---|
| 0.25 | **3.55** |
| 1 | 3.67 |
| 4 | 4.00 |
| 20 | 4.57 |
| 50 | 4.79 |

**Known limitation (state it, don't hide it):** the post-penalty route sits
*behind* the concentration gate, and a runner with real stranger history cannot
reach 70% without implausible farming. Fix is a recent window rather than
lifetime. **Not done — Project-II.**

### 6.3 Collusion rings

**The gap.** Viswanath et al. (SIGCOMM 2010) shows the social-graph defences are
really community detection, working only if the graph is a **faithful
observation** of reality. In every case the graph is something the platform
**watches**.

**What was built.** A ring is a **directed payment cycle among mutual friends**,
found with Tarjan's algorithm over the payment graph. Floors: **≥3 members**,
**≥2 laps**, each leg substantial **by value OR frequency**.

**Verified — [LIVE]** Seeded a real 3-person ring (₹600, 2 laps): sweep raised
**3 flags, severity 3**, `closure = 1.0`. On honest data the sweep returns **0**.

**Why 3 and not 2:** two friends alternating lunch is the most ordinary thing on
campus. A pair is *never* a ring — that case is handled by the rating weighting.

### 6.4 Telling an honest group from a closed one — the four filters

**No single test separates them.** Each filter clears a different kind of
innocent group.

| Filter | What it asks | Clears | Still cannot separate |
|---|---|---|---|
| 1. Structure | Is the group closed? | **nobody** — both score closure 1.0 | everyone |
| 2. Money cycle | Does value ever leave the group? | ordinary friend groups who also serve strangers | a group who genuinely only use each other |
| 3. z | Did our own app cause it? | insular groups who accept what they are offered | a group who deliberately prefer each other |
| 4. Language model | Do the errands read real? | genuine roommates — varied shops, odd hours, real notes | a careful ring that writes varied titles |
| 5. A human | — | — | — |

Filter 1 is where naive detection stops — **and it flags 6 of 6 entirely honest
groups** [SIM].

### 6.5 The central finding — our own matcher blinds our own detector

Cheng, Chen & Ye (IEEE ICDE 2019) co-assign people who have worked together
before, and **never examine that the policy decides who transacts with whom.**
Ours does the same, with a 1500 m friend boost.

**Out of every 100 errands a friend group posts — [SIM]**

| Friend boost | App hands them | Ring makes it | Extra they caused | Visible? |
|---|---|---|---|---|
| none | 40 | 100 | **+60** | obvious |
| medium 750 m | 88 | 100 | +12 | obvious |
| **OURS 1500 m** | **99** | **100** | **+1** | **invisible** |
| very high 2500 m | 100 | 100 | 0 | invisible |

> **The ring never changes its behaviour. Our routing catches up to it.**

*Simulation parameters: 60 students, 6000 errands, six honest friend groups
sharing hostel blocks, one ring taking each other's errands 85% of the time.*

### 6.6 The offer log

**The gap.** Maranzato & Pereira (IEEE LA-Web 2009) extract behavioural features
and score sellers **retrospectively**. Nothing records *why the platform made the
choice it made*, so the platform's own contribution can never be subtracted.

**What was built.** Every dispatch round writes one row: the candidate set, each
candidate's distance, trust, hops, reputation, penalty and final score, whether
the round was socially blind, and who accepted.

**Three design decisions:**

| Decision | Why | Verified |
|---|---|---|
| Save every part, not just the score | A total cannot be taken apart. *"Would he have won without the bonus?"* is unanswerable from −55 alone | **[TEST]** one shared formula for ranker and log — they cannot drift |
| One record per offer round | A re-offer happens to a different set of people; merging averages away the variation | **[LIVE]** 153 rounds recorded |
| Writing it can never break an errand | Analytics on a dispatch path must not stop somebody's dinner arriving | **[TEST]** sabotage the writer — errand still created and acceptable |

**The bug it caught.** On socially-blind rounds the system **ranked** without the
friend bonus but **logged** the score with it. The record contradicted what
happened, and every later estimate would have inherited that silently. Found by
running against the live stack — **all 213 tests were passing.**

**A worked log row:**

| Runner | Distance | Friend bonus | Score | Rank |
|---|---|---|---|---|
| Ujjwal (friend) | 695 m | − 750 m | **− 55** | 1 — took it |
| stranger A | 31 m | 0 | 31 | 2 |
| stranger B | 1200 m | 0 | 800 | 3 |

Without the bonus Ujjwal scores 695 and loses. **The app caused that pairing.**

### 6.7 Deliberate exploration

**The gap.** Perdomo et al. (ICML 2020, *performative prediction*) establish that
a deployed model changes the distribution it predicts. The standard remedy —
collecting data under a policy you did not optimise — has **never been proposed
to keep fraud detectable.**

**What was built.** With probability ε (default **5%**) a dispatch round is
ranked on distance alone: social term removed **and** hop ceiling lifted. **Both
must go together** — removing the boost while still hiding the errand from
strangers leaves the sample exactly as biased.

**What it buys — [SIM], at the deployed 1500 m setting:**

| | App hands them | Ring makes it | Extra | Visible? |
|---|---|---|---|---|
| no exploration | 99 | 100 | +1 | no |
| **5% blind** | **96** | **100** | **+4** | **yes** |
| 10% blind | 93 | 100 | +7 | yes |

**Verified — [LIVE]** the flip works on the real stack. Friend at 695 m, stranger
at 31 m:

| Round | Friend's score | Stranger's score | Offered first |
|---|---|---|---|
| Normal | **−53.6** | 31.0 | friend |
| Exploring | **694.6** | 31.0 | stranger |

**[TEST]** ε = 0.0 is an exact kill switch (500 draws, never explores); the rate
is read per call so it changes without a deploy.

**The cost:** 1 errand in 20 gets a worse-matched runner. A configuration value,
not a redesign.

### 6.8 The z check

**The gap.** Ring thresholds — group size, leg value, laps, concentration — are
**hand-tuned constants**. No test statistic, therefore no principled
false-positive rate.

**What was built.** The matcher already knows how likely each candidate was to
take each errand. Sum that across a group's rounds → what the policy
**expected**. Compare to what **happened**.

**Worked example, 200 errands:**

| | Rounds | The app expected | Honest group took | Ring took |
|---|---|---|---|---|
| Normal rounds | 190 | 178.6 | 177 | **190** |
| Socially blind rounds | 10 | 3.0 | 3 | **10** |
| **Total** | **200** | **181.6** | **180** | **200** |

| | Expected | Observed | Gap | Verdict |
|---|---|---|---|---|
| Honest group | 181.6 | 180 | −1.6 | **explained — no flag** |
| Ring | 181.6 | 200 | +18.4 | unexplained — continue |

**Same expectation for both**, because the app treats them identically. Only
behaviour differs — clearest in the blind rounds: **3 of 10 against 10 of 10**.
Ten blind errands carry about **40% of the evidence**; that is why 5% is enough.

**z** is a surprise score: below 3 the gap could be luck; at 3 or above it would
happen by chance less than once in a thousand times.

**Verified**
- **[SIM]** Naive flags **6/6 honest**; policy-conditioned flags **0/6** and
  still finds the ring
- **[SIM]** Co-located stress test — ring at the same desk still caught at 85%
  loyalty (z 3.7). It hides only by **restraint**, which rate-limits how much it
  can farm
- **[TEST]** Below 25 rounds it returns nothing and the detector behaves exactly
  as before — silence is not a verdict
- **[TEST]** Exculpatory only — a low z suppresses a flag; a high z never raises
  severity or manufactures one

### 6.9 LLM corroboration

**The gap.** Three roommates genuinely taking turns fetching dinner produce the
**identical triangle** and **identical circulation** as three students farming.
The graphs are mathematically the same shape. Structure answers *who* and *how
much*; neither answers ***what for***.

**What was built.** Local `qwen2.5:7b` via Ollama — no per-call cost, no user
data leaving campus. Asked one question, only about a group that already failed
the money check **and** the z check: *do these errands read as genuine campus
life?* It reads errand titles, vendors, times, notes and items from PostgreSQL —
and only errands **within** the group.

**Three non-negotiable rules:**
1. **Advisory only.** Never punishes, never withholds, never raises a severity.
   Its useful direction is **exculpatory** — clearing honest groups, where being
   wrong is cheapest.
2. **The text is written by the accused.** Fenced, labelled untrusted,
   schema-constrained. The worst a crafted note can do is move a number an admin
   can overrule. It can never become an instruction.
3. **Silence is neither innocence nor guilt.** Model down → returns nothing →
   everything behaves as before.

**Verified — [LIVE]** On the seeded ring: `reads_as_genuine: false`,
coherence 35, diversity 45, with its own observations — *"Near-identical titles
and intervals"*, *"Single vendor used for stationery"*.

*(Scores are 0–100 integers, not 0.0–1.0, because a 7B model asked for decimals
was **measured** returning `4.0` on a five-point scale it invented, which
Pydantic rejected — silently killing the channel.)*

**It creates zero flags.** `semantics.py` never constructs a `FraudFlag`; its
output is merged into the `details` of a flag that already exists.

### 6.10 Penalisation — what a flag actually does

| Mechanism | Stored in | Takes effect |
|---|---|---|
| Reputation deflation | `users.effective_reputation` | Matching score, automatic, no flag needed |
| Flag penalty | `fraud_flags` | +300 / +700 / +1200 m × decay, capped at 2000 m |
| Co-ring exclusion | flag `details.members` | Candidate removed **before** ranking |
| Escrow withholding | `escrow_holds` → PENDING_REVIEW | Wallet, price flags only |
| Strike ladder | `user_strikes` | warn → −0.5 stars → 7-day block → account |

**Points to land:**
- **Severity is hardcoded per rule, never model-decided.** If it responded to the
  model, an attacker could tune their errand titles to move their own penalty.
- A severity-3 penalty (**1200 m**) is deliberately **less** than the friend boost
  (1500 m). Suspicion demotes; it can never exclude.
- Penalties **fade to zero over 30 days** — an unreviewed accusation expires
  rather than pressing on someone's livelihood forever.
- Strike level 1 needs **three separate flagged errands** — a pattern, not an accident.
- **Idempotent by construction:** the level is a function of the flag count, so
  re-running can never double-punish.
- **Dismissal is one word** — `OPEN` → `DISMISSED` — and all four automatic
  effects stop at once, because each only matches OPEN or UPHELD.

---

## 7. Consolidated literature

| # | Paper | Owner | The gap it leaves |
|---|---|---|---|
| 1 | Jiang et al., *Graph-based trust evaluation*, ACM Comput. Surv., 2016 | Sanskriti | Decay by distance only; edge age never modelled |
| 2 | Chiou & Tu, IEEE Access, 2020 | Sanskriti | Closeness only ever raises weight; stops at rating, never reaches assignment |
| 3 | Fu & Liu, The Computer Journal, 2021 | Sanskriti | Trust from platform history only; no peer graph |
| 4 | Cheng, Chen & Ye, IEEE ICDE, 2019 | Chris | The policy decides who transacts, and that effect is never examined |
| 5 | Kamvar et al., *EigenTrust*, WWW, 2003 | Chris | Collusive-group weakness acknowledged, not solved |
| 6 | Viswanath et al., ACM SIGCOMM, 2010 | Chris | The graph is treated as observed, never as produced |
| 7 | Maranzato & Pereira, IEEE LA-Web, 2009 | Chris | Detection is retrospective and never reaches the matcher |
| 8 | Perdomo et al., *Performative prediction*, ICML, 2020 | Chris | Applied to prediction and pricing, never to fraud evidence |
| 9 | Gray & Reuter, *Transaction Processing*, 1993 | Ujjwal | Assumes the amount is known when the payment starts |
| 10 | Garcia-Molina & Salem, *Sagas*, ACM SIGMOD, 1987 | Ujjwal | Same assumption |
| 11 | Helland, CIDR, 2007 | Ujjwal | Same assumption |
| 12 | Li et al., *A survey on truth discovery*, SIGKDD Expl., 2016 | Ujjwal | Price settled after the fact, for analysis |
| 13 | Rousseeuw & Croux, JASA, 1993 | Ujjwal | Produces an accurate figure, not a safe margin |
| 14 | Gelman & Hill, CUP, 2007 | Ujjwal | A tool for judging shops, never had to fund a payment |
| 15 | Sarpal et al., arXiv:2310.04367, 2023 | Ujjwal | Structured catalogue SKUs, one price per item |
| 16 | Nigeria crowdsourced food prices, *Scientific Data*, 2023 | Ujjwal | Supports crowdsourced prices; not a payment mechanism |
| 17 | Kaplan & Menzio, NBER 21493, 2015 | Ujjwal | Documents price dispersion; no mechanism |
| 18 | Miao et al., arXiv:2102.09171, 2021 | Ujjwal / Chris | Data poisoning in crowdsourcing |
| 19 | Tarjan, *SIAM J. Computing*, 1972 | Chris | Algorithm used for cycle detection |

---

## 8. The three research gaps, stated together

**G1 — Escrow needs an amount that does not exist yet.** *(Ujjwal)*
One literature locks money but requires the amount in advance; another produces
the amount but only afterwards. Nobody uses a maintained price list to decide how
much to lock and how much room to leave.

**G2 — Trust is modelled without time.** *(Sanskriti)*
Graph trust decays with distance. An edge created this morning and one created
three years ago count identically — on a platform where relationships are free
and instant, that is the dimension an attacker moves in.

**G3 — The platform manufactures its own fraud evidence.** *(Chris)*
Trust-aware assignment promotes friends; collusion detection reads friends
transacting as evidence. Prior work assumes an **exogenous** graph — something
observed. Ours is **endogenous**, generated by our own routing. Performative
prediction supplies the right apparatus and has never been applied to fraud
evidence.

---

## 9. Style guidance for the final deck

**Plain white. Black text. No decoration.** Every slide follows one shape:

> **the gap in prior work → what we built → proof → what it changes**

**The slide carries the shape; the presenter carries the numbers.** Thresholds
are answers to questions, not the questions themselves. A slide containing
everything you were going to say means the room reads instead of listening.

Rewrites that worked:

| Do not put on a slide | Put this instead |
|---|---|
| "gates at ≥4 friend ratings and ≥70% concentration, then three routes…" | "We only look if 4+ friends rated them and most ratings come from friends. Then three questions — any yes raises a flag." |
| "≥3 members, ≥2 laps, each leg substantial by value OR frequency" | "Three or more people. The loop went round more than once. Each leg is real — big enough, or often enough." |
| "excess = observed − expected, standardised" | "What our app expected, versus what actually happened." |
| "ε-greedy socially-blind dispatch rounds" | "1 in 20 errands, we ignore friendship completely." |
| "confidence shrinkage — thin profile pulled toward neutral" | "A few ratings barely move your score. You have to earn your way up." |

**Say what is measured and what is simulated, before being asked.** The strongest
material in all three decks is where somebody found a flaw in their own system
and said so.

---

## 10. Figures available

All are matplotlib, generated by code in `docs/report/`, monochrome, regenerable.

| Figure | Shows | For |
|---|---|---|
| `fig_architecture` | Five-tier system architecture | Shared |
| `fig_sequence` | post → offer → accept → deliver → settle | Shared |
| `fig_escrow` | Escrow state machine + append-only ledger | Ujjwal |
| `fig_gantt` | Six sprints, Jul–Oct 2026 | Shared |
| `fig_sk_decay` | Two equal-length paths, different newest edge + maturity ramp | Sanskriti |
| `fig_sk_hops` | Trust and metres at 1–4 hops | Sanskriti |
| `fig_sk_attack` | What a same-day friendship buys | Sanskriti |
| `fig_trust_flow` | How one trust score is assembled | Sanskriti |
| `fig_social` | Honest group vs ring — identical structure | Chris |
| `fig_matching` | The dispatch pipeline with the ε branch | Chris |
| `fig_boost` | The ring never changes; our routing catches up | Chris |
| `fig_explore` | Exploration restores the gap | Chris |
| `fig_farming` | Karan vs Meera + the shrinkage curve | Chris |
| `fig_offerlog` | One annotated log row | Chris |
| `fig_llm` | Identical graphs, different errand text | Chris |
| `fig_penalty` | One flag row → four consequences | Chris |
| `fig_pipeline` | Offer log → z → flag → review, end to end | Chris |

---

## 11. Facts to keep consistent

- **260 tests passing** on the merged branch *(individual decks say 225 and 234 —
  both pre-merge)*
- Friend boost **1500 m** · rating **800 m/star** · flag penalties **300/700/1200 m**,
  capped **2000 m**, decaying over **30 days**
- Escrow headroom **+16%**, non-MRP lines only
- Exploration **ε = 5%** default
- Ring floors: **≥3 members, ≥2 laps**, leg substantial by value **or** frequency
- Maturity: floor **0.40**, full at **30 days**; hop decay **0.45**; max **4 hops**;
  tier-1 **2 hops for 45 seconds**
- z threshold **3.0**; minimum **25 rounds** before the check says anything
- LLM: `qwen2.5:7b`, local, advisory, creates **zero** flags

**Scope honesty — say these before being asked:**
- The peer resale marketplace is **specified, not implemented** — Project-II
- Real-money settlement through a licensed gateway is **designed, not wired**
- Comparison figures are **simulation**; the detector, log and exploration are
  verified on the running stack
- Every constant is **reasoned, not fitted** — fitting them against real campus
  data is Project-II
