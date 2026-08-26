# Social graph & trust-aware matching — handoff

Everything the social layer does, why it is shaped this way, and exactly where
the fraud/escrow work plugs in.

Branch: `feat/mobile-app`. The fraud/escrow work is on
`feat/payments-fraud-detection`. This document is written for whoever picks up
that side — it names the seams deliberately left open, and the things that are
*not* done so nobody rebuilds them by accident.

Deck objective this implements: **O2 — trust-first matching** ("rank nearby
Redis-GEO runners primarily by weighted social trust, gate out
integrity-flagged runners, then break ties by distance").

---

## 1. The one-paragraph version

Students add friends. Postgres owns the friendships; Neo4j holds a *derived*
copy used only for reads. When an errand is posted it is offered first to
people within 2 friendship hops, widening to 4 hops after 45s and to everyone
after 90s. Trust decays with hop distance and is **discounted when the
neighbourhood carrying it is closed**, because a tight group is simultaneously
the best trust signal and the best collusion substrate. Money flow is projected
into the same graph (`PAID` edges) but nothing reads it yet — that is the fraud
work's half.

---

## 2. Architecture

```
  request path                       async projection
  ────────────                       ────────────────
  POST /social/requests   ──┐
  POST /.../respond         │  writes    ┌─────────────┐
                            ├──────────► │  Postgres   │  ← SOURCE OF TRUTH
  (friendships table)     ──┘            │ friendships │
                                         └──────┬──────┘
                                                │ outbox row, same txn
                                                ▼
                                         ┌─────────────┐
                                         │   outbox    │
                                         └──────┬──────┘
                                                │ relay
                                                ▼
                                      Kafka: errandly.orders
                                                │
                          ┌─────────────────────┼──────────────────┐
                          ▼                     ▼                  ▼
                notification-service   settlement-service   social-graph-service
                                                                   │ MERGE
                                                                   ▼
                                                            ┌─────────────┐
                                                            │   Neo4j     │  ← DERIVED
                                                            │ User/FRIEND │     rebuildable
                                                            │      /PAID  │
                                                            └─────────────┘
                                                                   ▲
                                              read-only            │
                          matching / badges ───────────────────────┘
```

### Why Neo4j is a read model, not a database

Three properties fall out of this, and they are load-bearing:

1. **Nothing on a request path writes to Neo4j.** A graph write can never be
   the reason a user-facing action fails. The only writer is the projection
   consumer.
2. **The volume is disposable.** `docker compose down -v` on Neo4j loses
   nothing — replay the topic and it rebuilds.
3. **Reads fail soft.** Every read is behind a circuit breaker and returns a
   neutral value. Losing Neo4j degrades matching to distance-only ordering,
   which is what the platform did before any of this existed. It is never an
   outage.

If you need the graph to be authoritative for something, that is a design
change — say so explicitly rather than adding a write path.

---

## 3. Data model

### Postgres — `friendships` (source of truth)

`backend/app/modules/social/models.py`, migration `0013_friendships`.

| column | notes |
|---|---|
| `user_lo`, `user_hi` | the pair, **sorted**. `CHECK (user_lo < user_hi)` |
| `requested_by` | who asked — the ordering above discards direction |
| `status` | `PENDING` → `ACCEPTED` / `DECLINED`, or either → `BLOCKED` |
| `status_before_block` | so an unblock can restore, not guess |
| `blocked_by` | who blocked |

**Why sorted pairs:** without an ordering, `(A,B)` and `(B,A)` are different
rows — a pair could be befriended twice, or accepted from both ends into two
conflicting states. `pair()` in `models.py` is the only correct way to build
the key; use it.

Rows survive decline and block rather than being deleted: re-requesting someone
who declined should not be free, and an unblock needs something to unblock.

### Neo4j — nodes and edges

```cypher
(:User {id, name, degree, closure})
(:User)-[:FRIEND {since}]-(:User)          // undirected
(:User)-[:PAID {errand_id, amount, at}]->(:User)   // requester → runner
```

`degree` and `closure` are recomputed on a timer, not per event — one new
friendship changes the metrics of everyone in both neighbourhoods, so inline
recomputation would turn a single accept into an unbounded write.

---

## 4. Event contracts

Emitted by `app/modules/social/service.py` (`AGGREGATE = "SOCIAL"`):

| event | payload | when |
|---|---|---|
| `FriendshipAccepted` | `{user_a, user_b, at}` | a request is accepted |
| `FriendshipRemoved` | `{user_a, user_b}` | unfriend **or block** |

Only `ACCEPTED` ever reaches the graph. A pending or declined request is not a
trust signal and must never influence matching. A block emits `Removed` so a
blocked pair can never be matched to each other.

Consumed by `app/modules/social/projection.py`:

| event | effect |
|---|---|
| `FriendshipAccepted` | upsert both users, `MERGE` a `FRIEND` edge |
| `FriendshipRemoved` | delete the edge |
| `ORDER_COMPLETED` | write a `PAID` edge, `amount = reward + collect_amount` |

All writes use `MERGE`, never `CREATE`: delivery is at-least-once, so every one
of these can arrive twice and must be harmless when it does.

`ORDER_COMPLETED` is the same event `settlement-service` pays out on, so a
`PAID` edge exists for exactly the transactions the ledger recorded.
`items_total` is deliberately **excluded** from `amount` — it is not settled
through the platform (cash on handover; see `PaymentSummary` on mobile).

---

## 5. The trust model

```
trust = HOP_DECAY^(hops-1) × (1 − closure_penalty)
```

`app/modules/social/service.py`.

### Hop decay — `HOP_DECAY = 0.45`

| hops | trust | meaning |
|---|---|---|
| 1 | 1.0000 | your friend |
| 2 | 0.4500 | friend of a friend |
| 3 | 0.2025 | |
| 4 | 0.0911 | barely above a stranger |

Enough to prefer a connected runner over a stranger; not enough to outrank
someone much closer. Follows Jiang et al. (ACM CSUR 2016), reference [1] in the
deck.

### The closure discount — this is the novel part

On one campus, **the structure that makes someone trustworthy is the structure
that makes collusion easy.** Four friends taking turns running each other's
grocery errands — a category where spend is unverifiable because campus shops
issue no receipts — look to a naive social ranker like the *most* trustworthy
matches on the platform.

So trust flowing through a **closed** neighbourhood is worth less, not more:

```
closure = internal_edges / (internal_edges + boundary_edges)
```

over `N(u)` **excluding `u`**, with a knee at `CLOSURE_KNEE = 0.55` and a cap
at `MAX_CLOSURE_PENALTY = 0.7`.

Measured behaviour:

| shape | closure | penalty |
|---|---|---|
| fully-closed ring, n = 3…10 | 1.000 | 0.700 at every size |
| sociable hub, 8 mutually-unacquainted friends | 0.000 | 0.000 |

### Two measurement bugs already found and fixed — do not reintroduce them

**(a) Local clustering coefficient ranks the threat backwards.** It divides by
`deg×(deg−1)`, so a 4-person ring scored 0.5 while a 10-person hostel block
scored 0.8 — penalising large friendly groups and exempting small rings, which
is the opposite of the threat model. An added degree-dilution term made it
worse by explicitly protecting small cliques. **Closure is size-independent;
clustering is not.** That is why `u.closure` exists and `u.clustering` does not.

**(b) Including `u` in its own neighbourhood makes a star look like a clique.**
`u`'s own spokes count as internal edges, so a sociable hub scored 0.889 against
a ring's 0.875 — indistinguishable. The `WHERE x <> u` in `REFRESH_METRICS` is
what fixes this. It is not incidental.

### The honest limit — and where you come in

**Structure alone cannot separate a genuine four-person friend group from a
four-person collusion ring.** Both look identically closed. Structure says
"this group is capable of collusion", never "this group is colluding."

The discriminator is whether **value circulates** inside the group. That needs
the `PAID` edges, and it is the fraud work's half. This is why
`MAX_CLOSURE_PENALTY` is 0.7 and not 1.0: as it stands the term is a soft prior,
not a verdict, and it must not be treated as one until money-flow evidence
backs it.

---

## 6. Matching integration

`app/modules/errands/service.py` and `app/workers/consumers.py`.

### Staged offers — the important bit

Sorting by trust alone was **nearly a no-op** and this is easy to re-break.
Every candidate in a tier is published to in the same loop, milliseconds apart,
so reordering a simultaneous broadcast leaves a free-for-all race the nearest
stranger usually wins. Social preference comes from **when** each group is told:

| tier | when | audience | where |
|---|---|---|---|
| 1 | at post | ≤ 2 hops (friends + FoF) | `create_errand`, `SOCIAL_TIER_1_HOPS` |
| 2 | +45s | ≤ 4 hops | `SOCIAL_TIERS` in `consumers.py` |
| 3 | +90s | everyone, 8 km | `SOCIAL_TIERS` |

Tiers already sent are recorded as `ErrandEvent` rows (`OFFERED` /
`OFFER_BROADENED` with `social_tier`), so the audit trail *is* the state — a
worker restart cannot re-offer a tier.

**Cold-start escape hatch:** if tier 1 reaches nobody, `create_errand` falls
straight through to an open offer and records `social_tier: 0`. A student with
no friends yet — which is everyone on day one — must never be stranded. An
errand nobody sees is worse than an errand a stranger takes.

### Ranking within a tier

```
effective_distance = distance_m − trust × SOCIAL_WEIGHT_M     (1500 m)
```

Candidate *generation* stays purely spatial (Redis GEO). The graph only
reorders; it never widens the set, so a well-connected student cannot pull
errands from across campus.

### Failure semantics — please preserve this

`_safe_scores()` returns:

- `None` — the graph did not answer
- `{}` — the graph answered, nobody is connected

**Only `{}` may filter anyone out of an offer.** If you treat `None` as "nobody
is connected", a Neo4j outage silently disables social matching instead of
failing loudly. When fraud checks start gating candidates too, keep the same
distinction.

---

## 7. API surface

| method | path | notes |
|---|---|---|
| GET | `/social/friends` | accepted friends |
| GET | `/social/requests` | incoming pending |
| POST | `/social/requests` | `{user_id}`; sending back to someone who asked accepts |
| POST | `/social/requests/{id}/respond` | `{accept}` |
| DELETE | `/social/friends/{user_id}` | unfriend |
| POST | `/social/block/{user_id}` | block; also severs the graph edge |
| GET | `/social/search?q=` | campus-scoped, ≥2 chars |

Every errand response carries `connection`:

```json
{ "degree": 2, "label": "2nd", "via": "Rahul", "trust": 0.45 }
```

`degree: null, label: "R"` for a stranger. Computed server-side so every client
renders the same badge. Attached by `attach_connections()` and shown on errand
cards, errand detail, and in the live offer pub/sub payload.

Mutual-friend counts in search come from **Postgres, not the graph** — it is a
one-hop intersection Postgres answers exactly, and the search box must keep
working when Neo4j is down.

---

## 8. What is NOT done

> **Update (fraud/escrow side, `feat/payments-fraud-detection`):** the first two
> items below are now done — see §11. The rest still stand.

- ~~**Nothing reads `PAID` edges.**~~ Done: `modules/fraud/collusion.py`.
- ~~**No money-flow term in `closure_penalty`.**~~ Done, plus a `_direct_penalty()`
  for the one-hop case the original could not reach.
- **No integrity gating.** The deck's O2 says "gate out integrity-flagged
  runners". There is no flag, no event, and no filter. Suggested shape: a
  `RunnerFlagged` / `IntegrityCleared` event → a property on `(:User)` or an
  edge weight → filter in `_within_hops` or `_rank_with_scores`.
- **No GDS plugin.** Deliberately not installed: it downloads at container
  boot, so an offline start would fail the whole stack. `degree` and `closure`
  are plain Cypher. **Louvain community detection needs it** — add
  `NEO4J_PLUGINS: '["graph-data-science"]'` to the neo4j service when you get
  there, and expect a slower first boot.
- **No `PAID` backfill.** `social-graph-service` already committed offsets past
  the historical `ORDER_COMPLETED` events, so edges exist only for errands
  completed after this shipped. To rebuild, reset that consumer group's offset
  to earliest (the projection is idempotent, so replay is safe).
- **No decay/aging on edges.** A friendship from a year ago weighs the same as
  one from yesterday.
- **Constants are untuned.** `HOP_DECAY`, `CLOSURE_KNEE`, `SOCIAL_WEIGHT_M`,
  and the tier timings are reasoned defaults, not fitted to data. The pilot
  cohort is what should set them.

---

## 9. Running it

```bash
docker compose up -d          # now includes neo4j (browser :7474, bolt :7687)
docker compose exec backend alembic upgrade head
```

Neo4j dev credentials are in `docker-compose.yml` (`neo4j` / `errandly-dev`).

Each service builds its **own image** from `./backend` — `docker compose build
backend` does not rebuild `workers` or `relay`. Build all three after changing
dependencies, or you will get `ModuleNotFoundError` in the workers only.

Useful queries:

```cypher
MATCH (u:User) RETURN u.name, u.degree, u.closure ORDER BY u.closure DESC;
MATCH ()-[r:FRIEND]-() RETURN count(r)/2 AS friendships;
MATCH (a)-[p:PAID]->(b) RETURN a.name, b.name, p.amount, p.at;
```

---

## 10. Gotchas

- **3 pre-existing test failures** in `tests/test_email_verification.py`. They
  assert on the dev-mode `X-Dev-OTP` header, which real SMTP correctly
  suppresses. Not a regression — blank `smtp_host` in the test config to fix
  properly. The rest of the suite is 36 green.
- **`docker compose restart` does not re-read `env_file`.** Use
  `up -d --force-recreate`.
- **Display names are not unique.** Several accounts genuinely share one; the
  registration number is the only disambiguator. Search returns `student_id`
  for this reason — keep it in any UI you build.
- Friendship edges are **undirected**, so requester→runner hops equal
  runner→requester hops. One score serves both directions.


---

## 11. Money-flow half — collusion detection

Implemented on `feat/payments-fraud-detection` in `backend/app/modules/fraud/collusion.py`.
This closes the gap §5 named: *structure says a group is capable of collusion,
never that it is colluding.*

### Two signals, deliberately separate

**Circulation** — per user, the share of their settled platform value that moved
between them and their own friends. Stored on `(:User)` beside `degree` and
`closure`, refreshed on the same timer, read by the trust ranker. A gradient: it
discounts, it does not accuse. Knee at 0.60, and it stays 0 below
`MIN_CIRCULATION_VALUE`/`MIN_CIRCULATION_TXNS` so a new student with two errands
for a friend does not read as 100% internal.

**Closed money cycles** — a directed `PAID` cycle whose members are all mutual
friends, requiring `MIN_RING_LAPS` circuits and `MIN_RING_LEG_VALUE` on the
narrowest leg. This is a specific accusation about specific people, so it raises
a `COLLUSION_RING` flag for a human rather than acting on its own. Every member
is flagged, not one: the shape is symmetric and the graph shows no ringleader.

No money is withheld on a ring flag. A cycle is strong evidence about a *group*
but names no single dishonest errand, and those payouts settled long ago.

### The conjunction is the point

Neither half penalises anything alone. Closed-but-not-circulating is an ordinary
friend group; circulating-but-open is someone who trades with friends among many
others. Measured, on identical three-person triangles:

| | circulation | trust member→member | flagged |
|---|---|---|---|
| money goes round inside | 1.00 | **0.05** | yes |
| money goes out to campus | 0.00 | **1.00** | no |

That is the discrimination structure alone could not make.

### One correction to §5

`_closure_penalty()` only ever judged the **intermediary** on a multi-hop path.
In a three-person ring every member is one hop from every other, so there is no
intermediary and the penalty never fired — the ranker offered ring members each
other's errands at full trust, which is the exact path the fraud runs on.
`_direct_penalty()` covers the one-hop case, and is gated on money flow only:
structure alone must never discount a direct friend, or every close friend group
on campus gets punished for being close.

### Caps

`MAX_CLOSURE_PENALTY` stays 0.7 for structure alone. With money-flow
corroboration the cap rises to `MAX_CORROBORATED_PENALTY = 0.95` — the question
has changed from "could this group collude" to "is value going round in it".
Still short of 1.0: a corroborated ring may contain someone who simply has
friends, and 1.0 would erase them from matching entirely.

### Still open

- **Integrity gating** (§8) is still not done — flags exist now, but nothing
  filters a flagged runner out of a candidate set. The `None` vs `{}` rule in
  `_safe_scores()` is preserved and should stay that way when it lands.
- **Rings larger than 3.** The cycle search is a 3-cycle. A 4+ member ring is
  found only if it contains a triangle. GDS would be the honest tool here.
- **Constants untuned**, same caveat as §8.
