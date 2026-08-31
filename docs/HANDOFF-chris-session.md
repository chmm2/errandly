# Handoff — price integrity, farming, rings, decay, matching, wallet

For Ujjwal (and his Claude). Everything Chris and I changed in one session on
`feat/mobile-app`, why each change exists, and how to check it yourself.

Assumes `docs/SOCIAL_GRAPH.md` and `docs/HANDOFF-fraud-gating.md` as background.

| | |
|---|---|
| Branch | `feat/mobile-app` (has `feat/payments-fraud-detection` merged in) |
| Tests | **199 pass** |
| Migrations | `0018_scaled_tolerance`, `0019_claim_store` |
| New commands | `python -m app.rebuild_graph` |

---

## 0. Read this first — two things that will bite you

**The graph drifts silently, and nothing reports it.** Twice in one session I
found Neo4j holding a fraction of what Postgres held — once completely empty
against 11 live friendships. Nothing errored, because every graph read degrades
to a neutral value by design, so an empty graph is indistinguishable from a
campus where nobody has friends. Matching had quietly fallen back to
distance-only.

```bash
docker compose exec backend python -m app.rebuild_graph
```

Run that before any demo. **A parity check belongs in the scheduler before the
pilot** — compare Postgres accepted-friendship count against graph FRIEND count
and shout when they diverge. It is not built.

**Tests used to send real email.** Registration precedes most flows, so a full
run sent hundreds of OTPs through Chris's Gmail and eventually hit the daily
cap, taking seven unrelated tests down with a 550. `conftest.py` now blanks
`smtp_host`. This also fixed three verification tests that had been carried as
"known failures" for months — they were never broken, they were reaching the
internet.

---

## 1. Price scam detection

### The problem

A runner buys an unpriced item — a ₹10 masala tea — and reports it cost ₹29.
There is no receipt, no catalogue, no POS integration. The claim is the only
record.

### What was wrong

`tolerance_abs` was a **flat rupee line**, default ₹20. Its strictness ran
inverse to item price:

| item | reference | ₹20 flat line allows |
|---|---|---|
| masala tea | ₹10 | **+190% before flagging** |
| chicken puff | ₹20 | +100% |
| grocery run | ₹500 | +4% |

Measured before the fix: ₹29 × 3 for a ₹10 tea — **paid in full**, ₹57 of pure
profit, no flag.

### The fix — allowance scales with the item

```
allowance = clamp(reference × tolerance_pct, MIN_TOLERANCE_ABS, tolerance_abs)
          = clamp(reference × 0.40,          ₹5,                ₹20)
```

`tolerance_abs` keeps its value and **changes meaning**: from "the line" to
"the most the line may ever be". Expensive items behave exactly as before;
cheap ones stop being unprotected. `tolerance_pct = 0` restores the flat line
for a single item without a code change.

New column `reference_prices.tolerance_pct` (migration `0018`).

### The second problem — one price per campus

`ReferencePrice` was unique on `(campus_id, item_key)`. But the same puff is ₹23
at one canteen and ₹30 at another, and a single median lands in the gap. That is
wrong in **both** directions at once:

- an honest runner at the dearer shop reads as **persistently elevated**
- a runner inflating at the cheaper shop reads as **normal** — better
  camouflaged than the honest one

### The fix — judge against the shop

Claims now record `store_key` (migration `0019`): the vendor id when the errand
named one, otherwise the normalized pickup label. The reference is pulled toward
what that shop is observed to charge, shrunk by evidence:

```
ref_store = w × median(store) + (1 − w) × campus_reference
w         = n / (n + STORE_PRIOR)          n = DISTINCT RUNNERS, not claims
```

Partial pooling rather than a separate price per store — splitting outright
fragments samples until most items fall back to `NO_REFERENCE`.

**Two mistakes I made here, both worth knowing:**

1. **I first excluded `FLAGGED` claims from store learning.** Obviously right
   for the campus estimator, and a deadlock here: at a genuinely dear shop
   *every* honest claim is flagged against the campus number, so no unflagged
   evidence can ever accumulate. Four honest runners reporting ₹30 moved the
   estimate **zero**. The real defence is not the verdict filter but
   **independence** — one runner contributes one value, so a store only moves
   when several *different* runners agree.

2. **`STORE_MAX_DRIFT` was 0.60 and became the operative control.** From ten
   runners onward it clamped everything, so a shop genuinely charging ₹22
   against a ₹10 campus median stayed mispriced *forever* and every honest
   runner there was flagged. Raised to **1.5** — a sanity bound, not the
   limiter. The shrinkage does the limiting, and it requires distinct runners.

### Known cost

**Nine honest runners are flagged before a new shop's price establishes
itself.** Money is held pending review, not lost, but that is nine people and
nine admin decisions. Flags carry `store_reports` and the admin console says
plainly when it is under three that the claim was judged against the campus
reference because the shop has no price of its own yet.

**Open policy question for you and Chris:** reducing that further means paying
out on thin evidence, and `pickup_label` is free text — a fraudster could type a
fresh shop name every time. That is a money-policy call, deliberately not made.

### Test it

```bash
docker compose exec backend python -m pytest tests/test_store_pricing.py -q
```

Manually, in a shell:

```python
from decimal import Decimal
from app.modules.fraud.service import judge, effective_tolerance
# a ₹10 tea claimed at ₹29 must FLAG; at ₹14 it must not
```

---

## 2. Rating farming

### The attack

1. Scam strangers on price → take the flag and the reputation penalty
2. Reputation gates dispatch, so work dries up
3. Run errands for your own friends, collect genuine 5-star ratings
4. Float the score back up until matching offers you strangers again
5. Repeat

Every rating in step 3 may be **sincere** — the friend really was satisfied.
There is no forged data anywhere in this attack, which is why shilling-attack
detectors (which hunt inauthenticity) do not apply.

### Defence 1 — the discount tracks concentration, not friendship

A stranger's rating always counts in full. A friend's is discounted only in
proportion to how far past `CONCENTRATION_KNEE` the runner's mix sits, capped at
`MAX_RATING_DISCOUNT`. Rated by twenty strangers and five friends → **nothing
changes**. The discount attaches to the *shape of the evidence*, never the
relationship.

### Defence 2 — confidence shrinkage

```
matching_score = confidence × weighted_score + (1 − confidence) × 3.5
confidence     = weight_total / (weight_total + CONFIDENCE_PRIOR)
```

A farmed score does not become *low*, it becomes **low-confidence** and is
pulled toward neutral. Matching treats an unproven runner as unproven rather
than as dishonest, and recovery requires strangers — which is the behaviour the
platform wants back.

### What I changed — one rater, one vote

Weight used to accrue **per rating**, so 100 farmed ratings counted as 100
pieces of evidence. With the discount bottoming out at 0.75 each still carried
0.25, weight grew without bound, and **patience beat honesty**: 100 in-cluster
ratings scored 4.64 against 4.57 for 20 independent ones.

Weight now accrues **per person** — each rater contributes one vote carrying
their own mean:

| | raters | score |
|---|---|---|
| farm 20 ratings from 5 friends | 5 | 3.70 |
| farm 100 ratings from 8 friends | 8 | 3.80 |
| **farm 300 ratings from 8 friends** | 8 | **3.80** — saturates |
| honest 20 ratings from 20 strangers | 20 | **4.57** |

Removed at the root rather than by tuning the cap. Same rule the price estimator
and store adjustment already use. It costs an honest frequent customer nothing
real — twenty ratings from one person genuinely *is* one person's opinion.

`RatingProfile` now carries `in_raters`/`out_raters` (people) alongside
`in_cluster`/`out_cluster` (ratings). The admin console reports the ratings
counts, because "9 of 12 ratings came from friends" is what a reviewer wants to
read; the weighting uses the people counts.

### Three detection routes

Both gates first: `in_cluster ≥ 4` **and** `concentration ≥ 0.70`.

1. **Differential** — friends rate ≥ 0.8 stars higher than strangers (needs ≥ 3
   stranger ratings to compare against).
2. **Burst** — ≥ 2 high in-cluster ratings within 14 days of a penalty. Needs
   **no stranger ratings at all**, which is the point: a runner who has lost
   stranger work is exactly the one farming, so a detector requiring strangers
   would fail on the target case. Timing is the hardest signal to explain away.
3. **Never tested by a stranger** *(new)* — `in_cluster ≥ 15`,
   `out_cluster ≤ 1`, `repeat_ratio ≥ 2.5`. Catches the farmer who was never
   caught first: routes 1 and 2 both need something that has already happened
   (strangers to compare, or a prior penalty), so a patient attacker who farms
   from a standing start tripped neither.

**What it deliberately does not catch:**

| | repeat ratio | result |
|---|---|---|
| new runner, 4 ratings from 4 friends | 1.0 | clean |
| popular runner, 18 from **15** friends | 1.2 | clean |
| farmer, 18 from **5** friends | 3.6 | **FLAGGED** |

The signal is **repeat concentration, never friendship**.

### The gap that is left, and why rings matter

If a farmer recruits **breadth** instead of repeating — 80 friends each rating
once — they score **4.57**, exactly matching an honest runner, and trip none of
the three routes. Measured.

At the rating level those two things are *identical*: a genuinely popular
student with 80 friends who each order once looks the same. Tightening further
would punish popular students.

**What separates them is the money.** To get 80 friends to each post an errand,
either they genuinely paid (costs them 80 real payments, self-limiting, and not
fraud) or **the money came back** — which is the ring, and what makes 80 errands
free. That is why ring detection is the backstop for the evasion the rating
layer pushes attackers toward.

### Test it

```bash
docker compose exec backend python -m pytest tests/test_reputation.py -q
```

---

## 3. Ring detection — any size now

### What a ring is, and why it is run

**The platform never pays anybody.** The ledger has no fee or commission entry
type — only `TOPUP/HOLD/REFUND/REWARD/REIMBURSEMENT/CLAWBACK`. It holds a
requester's funds and releases them to the runner. So a closed money cycle is
**exactly zero-sum**: nobody gains a rupee, and nothing is stolen in the cycle.

The motive is **cost avoidance, not extraction**. Manufacturing reputation needs
completed errands with controllable ratings, which means the requester must be a
confederate — and that normally costs the confederate real money. Circulation
removes the cost:

| step | who posts | who runs | A | B | C |
|---|---|---|---|---|---|
| start | | | ₹100 | ₹100 | ₹100 |
| 1 | B | A | ₹120 | ₹80 | ₹100 |
| 2 | C | B | ₹120 | ₹100 | ₹80 |
| 3 | A | C | **₹100** | **₹100** | **₹100** |

One lap, everyone back where they started, **three completed errands and three
five-star ratings for ≈ ₹0**. The cycle is not the fraud; it is what makes the
farming in §2 economically sustainable. The extraction happens later, against
strangers, using the priority the manufactured reputation buys.

This is also why **no money is withheld on a ring flag** — nothing was
misappropriated in the cycle. That was already correct in your implementation.

### What was wrong

Detection matched a hard-coded three-hop Cypher pattern:

```cypher
MATCH (a)-[:PAID]->(b)-[:PAID]->(c)-[:PAID]->(a)
```

So **the cost of evading the platform's strongest fraud signal was one extra
member.** A four-person loop with no internal triangle produced nothing.

That became urgent with the rating work: the cheapest evasion of §2 is breadth,
and 80 people cannot circulate through a triangle. The rating layer was pushing
attackers directly into the money layer's blind spot.

### The fix — filter, then find components

1. Take payment edges between mutual friends
2. **Keep only edges that individually carry `≥ MIN_RING_LEG_VALUE` and
   `≥ MIN_RING_LAPS` separate errands**
3. Find strongly connected components of size `≥ MIN_RING_SIZE` in what remains

Every component of size ≥ 2 contains a cycle, so this finds loops of **any
length** without enumerating paths.

**Filtering before the search is the load-bearing detail.** Taking a minimum
across a whole component would let a ring hide behind one deliberate ₹1 payment
between two of its members, dragging the bottleneck under the threshold. An edge
that does not qualify is simply not part of the ring.

Tarjan is **iterative**, not recursive: the recursive form's depth is the
longest path in the graph, and a detector that raises `RecursionError` instead
of finding a ring is worse than one that is longer to read. Verified at 5000
nodes.

Verified detected at 3, 4, 6, 9, 20, 80 members. Chains, stars and two-person
pairs correctly ignored.

### Why two people are not a ring

`MIN_RING_SIZE = 3` on purpose — two friends buying each other lunch alternately
is the most ordinary thing on a campus. And the pair attack pays nothing anyway:
one rater means one vote, so 100 farmed errands score **3.55** against a neutral
3.50. Route 3 also flags them at 15 ratings. The rating layer handles pairs; the
money layer handles groups; the threshold between them is 3.

### Test it

```bash
docker compose exec backend python -m pytest tests/test_collusion.py -q
```

---

## 4. Temporal decay — two different things

### Money evidence ages (`MONEY_WINDOW_DAYS = 180`)

Circulation and ring detection counted **all-time** `PAID` edges. That is
inconsistent with the rest of the system in a specific, unfair way: **strikes
and flags already age out over 30 days, so the penalty decayed while the
evidence never did.** A ring that circulated eight months ago and stopped stayed
flagged forever, and a user whose first errands happened to be with friends
carried that ratio with no way back — and therefore no reason to stop.

Both queries now take a 180-day window. Two semesters: long enough that a ring
cannot clear itself by pausing a few weeks, short enough that a year of clean
conduct means something. Edges with no timestamp are **counted, not dropped** —
older rows predate the field and silently discarding evidence is the more
dangerous default.

**This required a fix first:** `ORDER_*` outbox events never carried a
timestamp, so `payload["at"]` was always `None` and **every `PAID` edge from
live traffic had a null date**. Verified: 9 live edges, 0 with timestamps. No
window could ever have applied. Order events now carry the transition time.

### Friendship edges mature (`FRIENDSHIP_MATURITY_DAYS = 30`)

Chris asked for this; I initially argued against it and substituted the money
window instead. He pushed back and was right — but the **direction** matters and
is the opposite of the obvious reading.

**A brand-new friendship is weak evidence** — it could have been created for
this errand. **An old one is strong.** So trust ramps *up* with age. Nothing
penalises an old friendship, because decaying old edges would punish long
friendships (better evidence) and stop nothing (rebuilding a network is free).

| friendship age | weight |
|---|---|
| today | 0.40 |
| 7 days | 0.54 |
| 15 days | 0.70 |
| 30+ days | 1.00 |
| unknown (predates the field) | 1.00 |

**Across a multi-hop path the newest edge governs.** A chain of trust is only as
established as its most recently created link. Concretely: you and Rahul have
been friends 400 days; yesterday Rahul accepted Arjun. Arjun scores **0.189**,
not 0.45 — because the only thing connecting you to Arjun is one day old.

That blocks a cheap attack: befriend one well-connected student and inherit
their entire network as 2nd-degree connections at full trust.

### Test it

```bash
docker compose exec backend python -m pytest tests/test_friendship_maturity.py -q
```

---

## 5. The matching algorithm, end to end

### Candidate generation stays spatial

Redis GEO returns the nearest available runners within `OFFER_RADIUS_M` (3 km),
capped at `OFFER_FANOUT` (5). **The graph never widens this set** — it only
reorders it — so a well-connected student cannot pull errands from across
campus.

### Staged dispatch — the part that makes social matching mean anything

Every candidate in a tier is published to within milliseconds of the others, so
*sorting* a simultaneous broadcast leaves a free-for-all race that the nearest
stranger usually wins. Social preference has to come from **when** each cohort
is told:

| tier | when | audience | radius |
|---|---|---|---|
| 1 | at post | ≤ 2 hops (friends + FoF) | 3 km |
| 2 | +45 s | ≤ 4 hops | 3 km |
| 3 | +90 s | anyone | 8 km |

Tiers already sent are recorded as `ErrandEvent` rows, so the audit trail *is*
the state and a worker restart cannot re-offer a tier. If tier 1 reaches nobody,
`create_errand` falls straight through to an open offer and records
`social_tier: 0` — a student with no friends yet (everyone on day one) must
never be stranded.

### Ranking within a tier

Everything is expressed **in metres** so the terms stay commensurable:

```
effective = distance_m
          − trust        × 1500      SOCIAL_WEIGHT_M
          − (rep − 3.5)  ×  800      REPUTATION_WEIGHT_M
          + integrity_penalty        300/700/1200 by severity, capped 2000
```

where

```
trust = HOP_DECAY^(hops−1) × (1 − closure_penalty) × maturity
```

The integrity cap is load-bearing: uncapped, accumulated flags would exceed any
plausible distance and silently convert a demotion into a ban nobody decided.

### Failure semantics — please preserve these

- `_safe_scores()` returns **`None`** for "the graph did not answer" and
  **`{}`** for "answered, nobody connected". **Only `{}` may filter anyone out
  of an offer.** Treating `None` as "nobody is connected" would let an outage
  silently disable social matching instead of failing loudly.
- `integrity.penalties()` returns `None` on failure → nobody is demoted.
- `co_ringed_with()` returns `None` on failure → nobody is excluded.

### Known bug, not fixed

`workers/consumers.py` `_offer_tier` passes `None` for reputations, so
**provenance-weighted reputation reorders the first offer and is ignored on
every timed escalation.** A runner demoted for a farmed reputation waits 45
seconds and is ranked as though clean — the same bypass-by-waiting you closed
for integrity flags. One-line fix plus fetching reputations there. Left alone
because it is your area and I did not want to change it silently.

---

## 6. Wallet (mobile)

New tab, **middle of five, raised 22 px out of the bar** with a ring in the page
background so the bar appears to part around it. Money is the thing people check
most and trust least.

**Add money** and **Retrieve money** are present and say plainly that payments
are not wired up yet. The production door is a gateway callback;
`POST /ledger/me/topup` is dev-only and 404s outside development.

The history is the substance. Grouped by day with Today/Yesterday named, and
every ledger type translated out of accounting language:

| ledger | wallet says |
|---|---|
| `HOLD` | 🔒 Held for an errand — ring-fenced until confirmed |
| `REWARD` | 🛵 You earned this — runner fee |
| `REIMBURSEMENT` | 🧾 Spending returned — what you paid at the counter |
| `REFUND` | ↩ Returned to you — the errand did not go ahead |
| `CLAWBACK` | ↖ Taken back — reversed after a review |
| `TOPUP` | ＋ Money added |

`HOLD`, `CLAWBACK` and `REIMBURSEMENT` are correct in a ledger and exactly wrong
for someone checking why their balance moved. Direction is carried by a **sign
as well as colour**. Escrow is shown rather than hidden — that money has already
left the balance, and naming it explains where it went.

**Not built:** pagination. The endpoint returns only `RECENT_ENTRY_LIMIT`
entries, so there is no full history yet.

---

## 7. Errand posting (mobile) — structured lists

The shopping form posted a **typed sentence** into `title`. The backend has
accepted `list_items` with quantities all along, so nothing downstream could act
on a phone-posted errand: the runner reports a unit price per line, and **prose
cannot be priced.** The entire price-integrity chain in §1 had no input.

Now each line is its own row: name + quantity stepper, with "+ Add item".

Also:
- **Removed "pick up from" for shopping** — which shop is nearest is the
  runner's call. Sent as `"Runner's choice"`.
- **Removed "what do you need?" from parcel and gate** — the parcel exists and
  is already paid for. Both now ask **who it is from**, with different lists:
  couriers at the collection point (Delhivery, Blue Dart, DTDC, Ekart, India
  Post, Amazon, Flipkart) and quick commerce at the gate (Swiggy, Zomato, Zepto,
  Blinkit, Instamart).
- `title` and `pickup_label` are required server-side and are now **derived**.
- Reward input was `flex: 1` and pushed the ₹50 preset off the screen edge.
  Fixed at 74 px.

**Note:** errands posted from the phone before this have no `list_items`, so
their price claims still hit `NO_REFERENCE`. Only new ones are checkable.

---

## 8. A real access-control leak, fixed

`get_errand` checked campus membership **and nothing else**. Any student could
fetch **any errand by id** and read its requester, assigned runner, progress,
items and amounts — runs they had no part in, errands finished months ago.

The rule now: **your own errands, plus work that is still OPEN.** An open errand
is an offer to the campus and a runner deciding whether to take it must be able
to read it; once someone accepts, it becomes two people's business. **404 rather
than 403** — confirming an errand exists is itself something a stranger should
not learn. Admins exempt.

Four existing tests encoded the weaker behaviour and were updated, not worked
around: two expected `403` where a stranger now gets `404`, and two expected a
`200 with fields stripped` — the old approach, which still confirmed existence
and still leaked progress and amounts. **One 403 is deliberately untouched:** a
would-be runner is still refused the handoff OTP on an open errand they can
otherwise see. That is a *party denied one field*, not a stranger denied the
errand.

---

## 9. The language model

`qwen2.5:7b` on Ollama, `LLM_PROVIDER=ollama` in `backend/.env`.

Those channels had **never executed on Chris's machine** — `LLM_PROVIDER` was
unset, so `semantics.enabled()` was `False` and everything degraded to "no
opinion" exactly as designed, which is why nothing looked broken.

**The review-reading channel is now off by default** (`review_analysis_enabled
= False`). I ran your eval harness against a live model and independently
reproduced your negative result:

| | your run | my run |
|---|---|---|
| separation | −0.9 pts | **+2.8 pts** |
| false clearance | 1/3 | **1/3** |
| controls passed | 1/2 | 1/2 |

Two authors, two runs, both ≈ zero. And it fails in **both** directions on the
cases that decide whether it is safe: a farmed history with varied wording
scored 72 and was **cleared**, while an honest runner whose friends rate without
writing scored 30 and was **not**. An advisory that clears the dishonest and
fails the honest is worse than no advisory, even annotation-only.

Gated rather than deleted — the prompt deserves another attempt and
`evals/run_eval.py` is where to iterate. Turn it on when the harness shows real
separation. **The errand-text channel is untouched and stays on** (41.7 pts).

The model choice is not incidental: config records that `llama3.2:3b` returned
`reads_as_genuine=True` for a history its own observations had called
suspicious. Chris's machine had only the 3B until now.

---

## 10. Every constant, in one place

**All unfitted.** These are reasoned defaults, not values derived from data, and
they belong in the paper's limitations and in the ablation sweep.

```
PRICE            MIN_TOLERANCE_ABS ₹5      tolerance_pct 0.40 (per item)
                 STORE_PRIOR 6            STORE_MIN_RUNNERS 3
                 STORE_MAX_DRIFT 1.50     PATTERN_WINDOW_DAYS 30
                 NEAR_THRESHOLD_SHARE 0.60  NEAR_THRESHOLD_MIN_CLAIMS 4
                 SEVERITY_BANDS ≤₹20 → 1, ≤₹50 → 2, else 3

REPUTATION       CONCENTRATION_KNEE 0.50  MAX_RATING_DISCOUNT 0.75
                 CONFIDENCE_PRIOR 8.0     NEUTRAL_RATING 3.5
                 FARMING_MIN_IN_CLUSTER 4 FARMING_CONCENTRATION 0.70
                 FARMING_DIFFERENTIAL 0.8
                 POST_PENALTY_DAYS 14     POST_PENALTY_BURST 2
                 UNPROVEN_MIN_IN_CLUSTER 15  UNPROVEN_MAX_OUT_CLUSTER 1
                 UNPROVEN_REPEAT_RATIO 2.5

COLLUSION        MONEY_WINDOW_DAYS 180    MIN_RING_SIZE 3
                 MIN_RING_LAPS 2          MIN_RING_LEG_VALUE ₹150
                 MIN_CIRCULATION_VALUE ₹300  MIN_CIRCULATION_TXNS 4

TRUST            HOP_DECAY 0.45           CLOSURE_KNEE 0.55
                 MAX_CLOSURE_PENALTY 0.70 MAX_CORROBORATED_PENALTY 0.95
                 FRIENDSHIP_MATURITY_DAYS 30  NEW_FRIENDSHIP_FLOOR 0.40

MATCHING         SOCIAL_WEIGHT_M 1500     REPUTATION_WEIGHT_M 800
                 NEUTRAL_REPUTATION 3.5   SOCIAL_TIER_1_HOPS 2
                 OFFER_RADIUS_M 3000      OFFER_FANOUT 5
                 SOCIAL_TIERS  +45s → 4 hops @3km,  +90s → open @8km
```

---

## 11. How to run everything

```bash
# stack
docker compose up -d
docker compose exec backend alembic upgrade head
docker compose exec backend python -m app.seed

# the graph is derived — rebuild it whenever it looks wrong
docker compose exec backend python -m app.rebuild_graph

# full suite (against the separate test DB; the dev DB has demo data)
docker compose exec -T \
  -e DATABASE_URL="postgresql+asyncpg://errandly:errandly@db:5432/errandly_test" \
  -e REDIS_URL="redis://redis:6379/1" \
  backend python -m pytest tests/ -q

# the language channels, against a live model
docker compose exec backend python -m evals.run_eval --repeats 1
```

If the test DB does not exist:

```bash
docker compose exec db psql -U errandly -d postgres -c "CREATE DATABASE errandly_test;"
docker compose exec db psql -U errandly -d errandly_test \
  -c "CREATE EXTENSION IF NOT EXISTS postgis; CREATE EXTENSION IF NOT EXISTS citext; CREATE EXTENSION IF NOT EXISTS pgcrypto;"
docker compose exec -T -e DATABASE_URL="postgresql+asyncpg://errandly:errandly@db:5432/errandly_test" \
  backend alembic upgrade head
```

Useful graph queries:

```cypher
MATCH (a:User)-[r:FRIEND]-(b:User) RETURN a, r, b;
MATCH (u:User) RETURN u.name, u.degree, u.closure, u.circulation ORDER BY u.closure DESC;
MATCH (a)-[p:PAID]->(b) RETURN a.name, b.name, p.amount, p.at;
```

---

## 12. What is still open

| | |
|---|---|
| **Graph parity check** | Nothing detects drift. Two silent failures in one session. Before the pilot. |
| **`_offer_tier` reputations** | Demotion bypassable by waiting 45 s. Your area, one-line fix. |
| **Cold-start flags** | ~9 honest runners flagged before a new shop learns its price. Policy call. |
| **Free-text `pickup_label`** | A fraudster can type a fresh shop name each time to stay at low `store_reports`. |
| **Wallet pagination** | Recent entries only. |
| **Review channel** | Off. Fix the prompt against the harness, or report it as a limitation. |
| **Test order-dependence** | One test fails intermittently in full runs, passes in isolation. |
| **Every constant above** | Unfitted. The ablation in `docs/PAPER.md` §VI-B is what sets them. |
