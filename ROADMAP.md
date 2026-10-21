# Errandly — Delivery Roadmap

3 people · 2-week sprints · ~15-week semester. Tick boxes as you finish. Protect the **Must-have** column;
if a sprint slips, cut from **Could-have**, never from **Must-have**.

**Roles (primary owner; everyone reviews):** Chris = backend/services · Ujjwal = frontend/UX · Dhanjith = infra/data.
**Definition of Done:** merged via PR (feature → dev, dev → main at sprint end) · tests green in CI · runs in `docker compose up` · demoable · README updated.

Each sprint lists the **system-design patterns** it implements (see the Pattern Ledger at the bottom —
that table is the interview/viva cheat sheet).

---

## Sprint 0 — Foundations (Week 1) ✅
- [x] Repo, structure, .gitignore, README, ROADMAP
- [x] Docker Compose (Postgres+PostGIS, Redis) + backend Dockerfile
- [x] FastAPI skeleton + health endpoint
- [x] SQLAlchemy async + Alembic wired
- [x] GitHub Actions CI (lint + test, backend + frontend)
- **Demo:** `docker compose up` runs; CI green.
- **Patterns:** health endpoint monitoring · asynchronism (async I/O end-to-end)

## Sprint 1 — Auth & walking skeleton (Weeks 2–3) ✅
- [x] users / auth_credentials / refresh_tokens models + migration
- [x] register / login / refresh endpoints + JWT + argon2
- [x] account-status guard (PENDING/ACTIVE/SUSPENDED/BANNED); Redis JWT blacklist
- [x] React shell: login/register, protected routes, bare errand form
- [x] Seed script (campus, test user)
- **Demo #1:** register → admin approve → login → /me. ✔ verified in browser
- **Patterns:** idempotent operations (jti, single-use refresh rotation) · retry-storm avoidance
  (single-flight client token refresh) · stateless services (JWT ⇒ horizontally scalable API)

## Sprint 2 — Order core, lifecycle & contention (Weeks 4–5) ✅
- [x] errands / errand_events tables + migration (PostGIS points, GIST index)
- [x] state machine with guarded transitions (OPEN→ACCEPTED→IN_PROGRESS→DELIVERED→COMPLETED / CANCELLED)
- [x] **accept-race handling:** Redis `SET NX` lock (fast fail) + Postgres `SELECT FOR UPDATE` (correctness)
- [x] optimistic locking (`version` column); cancel-before-pickup rules
- [x] event-sourced audit trail (`errand_events` append-only)
- [x] **rate limiting:** Redis fixed-window limiter on login + errand creation (429 + Retry-After)
- [x] requester order flow UI (create with geolocation, feed, status, history) + login redesign
- [x] integration tests for every transition (incl. illegal ones) + concurrent-accept race test
- **Demo #2:** two runners race to accept one errand — exactly one wins; full lifecycle with audit
  trail. ✔ demoed live (3 racers: one 200, two 409; audit trail CREATED→…→COMPLETED)
- **Patterns:** distributed lock (+ TTL) · pessimistic vs optimistic locking · event sourcing ·
  state machine · rate limiting/throttling · idempotency

## Sprint 3 — Geo, matching & live tracking (Weeks 6–7) ✅
- [x] runner_profiles / runner_status; availability toggle
- [x] matching engine (Redis GEOSEARCH, nearest-5 fanout; load via cap — direction scoring deferred)
- [x] load cap on accept *(offer timeout → broaden retry loop moved to Sprint 4 — it's a
  scheduler job, and Sprint 4 owns the worker process)*
- [x] browser Geolocation capture; runner dashboard
- [x] WebSocket live order status; location updates **throttled** (client ≤1/10s, server ≤1/5s)
- [x] **order tracking page:** Leaflet + OpenStreetMap (no API key), runner position live on
  the map + status stepper timeline built from errand_events *(UX ref: Enatega rider tracking)*
- [x] **saved drop points:** recent drops ("Block A Room 402") as one-tap chips on the form
- [x] **verified handoff:** `fulfillment_type` + `external_ref` + `collect_amount`; OTP
  encrypted at rest, disclosed only to the assigned runner post-accept, reads audited
- **Demo #3:** order → nearest runner live push → accept → runner unlocks the pickup OTP
  (requester sees who viewed it) → live tracking. ✔ verified in browser (marker moved live)
- **Patterns:** CAP in practice (Postgres = consistent truth, Redis GEO = eventually-consistent
  derived index) · cache-aside · async request-reply (WebSockets) · scheduler/timeout jobs

## Sprint 4 — Kafka backbone & timetable (Weeks 8–9) ✅
- [x] **transactional outbox:** ORDER_* events written atomically with orders, relayed to Kafka
  by a worker polling with `FOR UPDATE SKIP LOCKED`
- [x] extract Notification + Analytics as idempotent, competing consumers (processed_events
  dedupe: at-least-once delivery + idempotency = effectively-once)
- [x] circuit breaker + retry-with-backoff around producer/consumer side effects
- [x] timetable_slots (Postgres EXCLUDE overlap constraint) + enforcer (auto-block runners:
  can't go online in class; matching skips in-class runners; job sweeps the GEO index)
- [x] offer timeout → broaden retry loop (scheduler job in the worker)
- [x] timetable UI, live notifications bell (WS), basic analytics (read model + summary API;
  UI surface lands with the Sprint 6 admin dashboard)
- ✔ demoed: bell lit live through outbox→Kafka→consumer→WS; enforcer auto-blocked an online
  runner when class started
- **Demo #4:** one event fans out to 2 services; kill a consumer mid-stream, restart, no dupes;
  runner auto-blocks during class.
- **Patterns:** pub/sub · queue-based load leveling · competing consumers · transactional outbox ·
  circuit breaker · retry with backoff · strangler-fig extraction (first seam split)

## Sprint 5 — Catalog, trust, chat, payments (Weeks 10–11) ◀ current
- [ ] **RBAC:** `role` on users (STUDENT/VENDOR/ADMIN); `require_vendor` guard; student_id/
  campus-email rules become role-conditional. Vendors are onboarded by admin (no self-signup).
- [ ] **vendor catalog:** vendors (owner_user_id, open/closed) + menu_items tables; **vendors
  maintain their own menus** — ownership-checked CRUD, per-item sold-out toggle
- [ ] **vendor portal UI:** one screen — my menu by section, add/edit/price/stock toggle
- [ ] **Swiggy-style menu UI:** vendor card grid → menu page with sticky section nav → cart;
  cart snapshots item name+price into `errand_items` (old orders keep the price actually paid)
- [ ] **order-time revalidation:** cart is client-side, so POST /errands re-checks every item
  against the live menu (still available? price changed?) and rejects with a diff the UI shows
- [ ] cache-aside on menus (read-heavy → Redis) **with invalidation on vendor edits** —
  sold-out must reflect instantly, not after a TTL; **fallback-to-stale** if Postgres is slow
  (a slightly old menu beats an error page)
- [ ] ledger_entries / wallets; settlement on delivery incl. `collect_amount` reimbursement
  (runner fronts cash at pickup → repaid + reward; KARMA now, UPI later)
- [ ] ratings → reputation → feedback into matching; **post-delivery rating modal at handoff**
- [ ] **runner earnings summary** ("₹240 this week · 12 deliveries") from the ledger
- [ ] menu UX details *(ref: Enatega)*: sticky category tabs, sold-out item states,
  persistent bottom cart bar ("2 items · ₹110 · View cart")
- [ ] MongoDB chat + notifications feed; chat UI
- [ ] CQRS-lite: denormalized read model for the runner feed
- [ ] batching (same store + nearby zone + time window) — first to cut if the sprint slips
- **Demo #5:** canteen owner logs into the portal, marks an item sold out — it greys out on a
  student's menu instantly; order 2 items; runner fronts cash, ledger repays; live chat.
- **Patterns:** CQRS/materialized view · ledger (append-only money) · polyglot persistence ·
  cache-aside · snapshot vs reference (price at order time)

## Sprint 5.5 — Escrow payments & price-claim fraud (branch: `feat/payments-fraud-detection`)
- [x] **wallet + escrow:** balance is derived (SUM credits − debits, never stored); `LedgerEntry`
  gains a `direction` so escrow can debit. Order time places a **hold** for
  items + reward + collect_amount; delivery **releases** it; cancel **refunds** it. A payout can
  never exceed its hold — `released_amount <= amount` is a DB CHECK, not just service logic.
- [x] **runner price claims:** runner reports what they actually paid at pickup
  (`POST /fraud/errands/{id}/claims`). Reimbursement is drawn from the JUDGED claim, never from
  the amount asked for.
- [x] **reference prices (non-MRP items):** admin sets a hard **band** per item; a robust
  estimator moves the reference only *inside* that band; band-edge drift raises a **proposal**
  for admin approval. Admins click approve, they don't type data.
- [x] **anti-poisoning:** estimate = median of *per-runner* medians, so volume buys no influence —
  one runner claiming ₹40 two hundred times contributes a single ₹40. FLAGGED claims are excluded
  from the evidence entirely. This is what stops the detector being trained by the fraud it polices.
- [x] **escalation ladder:** flagged *errands* (not lines) in a 30-day window →
  3 = warning · 5 = reputation penalty · 8 = runner block (7d) · 12 = account suspension.
  One high claim is never punished; the pattern is.
- [x] **appeal path:** admin uphold/dismiss actually moves money — dismissing pays the runner the
  withheld amount and restores the claim as reference evidence.
- **Demo:** runner claims ₹40 for a ₹20 chicken puff → paid ₹20, ₹40 held, flag raised; do it on
  three errands → warning lands; admin dismisses one → the money moves back.
- **Patterns:** escrow / hold-release · derived balances · robust estimation under adversarial
  input · human-in-the-loop bounds · graduated sanctions

## Sprint 6 — Admin, security, observability, scale-out (Weeks 12–13)
- [ ] disputes workflow; admin suspend/ban → Redis blacklist
- [ ] SQLi/XSS/CSRF audit; secrets hygiene
- [ ] admin dashboard + config panel
- [ ] **nginx load balancer** fronting 2 backend replicas in compose (proves statelessness)
- [ ] Prometheus + Grafana (latency, Kafka lag, Redis hits); audit logs; backups
- **Demo #6:** kill one backend replica live — traffic keeps flowing; admin suspends user
  (instant block); Grafana live; dispute resolved.
- **Patterns:** L7 load balancing · horizontal scaling · gateway routing/offloading ·
  monitoring & instrumentation · gatekeeper

## Sprint 7 — Integration, testing, docs, demo (Weeks 14–15)
- [ ] end-to-end integration + load test (1000 concurrent)
- [ ] team bug bash; fix critical/high; security pass
- [ ] docs (architecture, API, deploy), README, demo script + rehearsal
- [ ] viva prep (each person explains their seam); backup demo video
- **Demo #7 (final):** happy path + 2 edge cases + architecture walkthrough.

---

## Pattern Ledger — roadmap.sh concept → where it lives in Errandly

| Concept | Where | Sprint |
|---|---|---|
| Idempotent operations | JWT jti, single-use refresh, Kafka consumers | 1, 4 |
| Retry storm (avoided) | single-flight token refresh in `frontend/src/lib/api.ts` | 1 |
| Health endpoint monitoring | `/health` + Docker healthchecks | 0 |
| Stateless services | JWT auth ⇒ any replica can serve any request | 1, 6 |
| State machine | errand lifecycle, guarded transitions | 2 |
| Event sourcing | `errand_events` append-only audit | 2 |
| Distributed lock | Redis SET NX + TTL on accept; row lock as backstop | 2 |
| Pessimistic vs optimistic locking | `SELECT FOR UPDATE` vs `version` column | 2 |
| Rate limiting / throttling | Redis window on login + create | 2 |
| CAP / eventual consistency | Postgres truth vs Redis GEO derived index | 3 |
| Cache-aside | Redis in front of Postgres reads; vendor menus | 3, 5 |
| Least-privilege secret disclosure | pickup OTP gated to assigned runner + SECRET_VIEWED audit | 3 |
| Snapshot vs reference | errand_items copy name+price at order time | 5 |
| RBAC + ownership auth | role column + require_vendor; vendors edit only their own menu | 5 |
| Cache invalidation on write | vendor sold-out toggle busts the menu cache immediately | 5 |
| Throttling / backpressure | WS location updates capped at ~1 per 5–10s | 3 |
| Graceful degradation (stale fallback) | serve last-known menu from Redis if Postgres is slow | 5 |
| Order-time revalidation | client cart re-checked against live menu at POST /errands | 5 |
| Async request-reply | WebSocket order tracking | 3 |
| Pub/sub, load leveling, competing consumers | Kafka backbone | 4 |
| Transactional outbox | orders + events atomically → Kafka relay | 4 |
| Circuit breaker, retry+backoff | around consumer side effects | 4 |
| Strangler fig | modular monolith → services at seams | 4+ |
| CQRS / materialized view | runner-feed read model | 5 |
| Polyglot persistence (SQL vs NoSQL) | Postgres / Redis / MongoDB, each justified | 1–5 |
| L7 load balancing, horizontal scaling | nginx + 2 API replicas | 6 |
| Monitoring / instrumentation | Prometheus + Grafana + audit logs | 6 |
| Sharding (designed-for, not built) | `campus_id` on every table = natural shard key | — |
| Escrow / hold-release | `escrow_holds` + `ledger.place_hold/release_hold` | 5.5 |
| Derived balances (no stored totals) | balance = SUM(credits) − SUM(debits) | 5.5 |
| Idempotent payout | unique (errand, user, entry_type) + SAVEPOINT on conflict | 5.5 |
| Robust estimation vs. adversary | median of per-runner medians; MAD outlier rejection | 5.5 |
| Human-in-the-loop bounds | admin band caps what the estimator may write | 5.5 |
| Graduated sanctions | flag count in window → warning → block → suspension | 5.5 |
| **Consciously rejected** | CDN, geo-DNS, federation, service discovery, BFF — single campus, single client; know *why* | — |

**Interview rule: every pattern must carry its failure story** (lock holder crashes → TTL + fencing;
consumer dies mid-message → idempotency + at-least-once; Redis lies → row lock backstop).

---

## MoSCoW — what's droppable
| Must-have (never cut) | Should-have | Could-have (cut first) |
|---|---|---|
| Auth + verification | Timetable block | Batching / route opt |
| Order lifecycle + audit + locking | Ratings/reputation | MongoDB chat |
| Runner matching + geo | Kafka async split | gRPC internal call |
| Live tracking | Payment ledger | Full Prometheus/Grafana |
| Admin suspend/ban | Disputes | Multi-campus UI |
| Rate limiting | nginx LB demo | CQRS read model |
| Verified handoff (OTP/order no.) | Vendor menus + cart UI (vendor-maintained) | Menu photos/uploads |

**Risk peaks:** Sprints 3 & 4. Keep one catch-up day per sprint for Docker/Kafka/integration gremlins.
