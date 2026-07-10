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

## Sprint 2 — Order core, lifecycle & contention (Weeks 4–5) ◀ current
- [ ] errands / errand_events tables + migration (PostGIS points, GIST index)
- [ ] state machine with guarded transitions (OPEN→ACCEPTED→IN_PROGRESS→DELIVERED→COMPLETED / CANCELLED)
- [ ] **accept-race handling:** Redis `SET NX` lock (fast fail) + Postgres `SELECT FOR UPDATE` (correctness)
- [ ] optimistic locking (`version` column); cancel-before-pickup rules
- [ ] event-sourced audit trail (`errand_events` append-only)
- [ ] **rate limiting:** Redis fixed-window limiter on login + errand creation (429 + Retry-After)
- [ ] requester order flow UI (create with geolocation, feed, status, history) + login redesign
- [ ] integration tests for every transition (incl. illegal ones) + concurrent-accept race test
- **Demo #2:** two runners race to accept one errand — exactly one wins; full lifecycle with audit trail.
- **Patterns:** distributed lock (+ TTL) · pessimistic vs optimistic locking · event sourcing ·
  state machine · rate limiting/throttling · idempotency

## Sprint 3 — Geo, matching & live tracking (Weeks 6–7)  ⚠ risk peak
- [ ] runner_profiles / runner_status; availability toggle
- [ ] matching engine (Redis GEOSEARCH, score by proximity+load+direction)
- [ ] offer → accept/timeout → broaden retry loop; load cap
- [ ] browser Geolocation capture; runner dashboard
- [ ] WebSocket live order status
- [ ] **verified handoff** for gate/parcel pickups: `fulfillment_type` + `external_ref` +
  `collect_amount` on errands; delivery OTP stored gated — disclosed **only to the assigned
  runner after accept** via a dedicated endpoint, every view logged as a `SECRET_VIEWED` event
- **Demo #3:** order → nearest runner live push → accept → runner unlocks the pickup OTP
  (requester sees who viewed it) → live tracking.
- **Patterns:** CAP in practice (Postgres = consistent truth, Redis GEO = eventually-consistent
  derived index) · cache-aside · async request-reply (WebSockets) · scheduler/timeout jobs

## Sprint 4 — Kafka backbone & timetable (Weeks 8–9)  ⚠ risk peak
- [ ] **transactional outbox:** ORDER_* events written atomically with orders, relayed to Kafka
- [ ] extract Notification + Analytics as idempotent, competing consumers
- [ ] circuit breaker + retry-with-backoff around consumer side effects
- [ ] timetable_slots (overlap-exclusion) + enforcer job (auto-block runners)
- [ ] timetable UI, notifications panel, basic analytics
- **Demo #4:** one event fans out to 2 services; kill a consumer mid-stream, restart, no dupes;
  runner auto-blocks during class.
- **Patterns:** pub/sub · queue-based load leveling · competing consumers · transactional outbox ·
  circuit breaker · retry with backoff · strangler-fig extraction (first seam split)

## Sprint 5 — Catalog, trust, chat, payments (Weeks 10–11)
- [ ] **vendor catalog:** vendors + menu_items tables (campus canteens/stores, sectioned menus)
- [ ] **Swiggy-style menu UI:** vendor card grid → menu page with sticky section nav → cart;
  cart snapshots item name+price into `errand_items` (old orders keep the price actually paid)
- [ ] cache-aside on menus (read-heavy, write-rarely → Redis in front of Postgres)
- [ ] ledger_entries / wallets; settlement on delivery incl. `collect_amount` reimbursement
  (runner fronts cash at pickup → repaid + reward; KARMA now, UPI later)
- [ ] ratings → reputation → feedback into matching
- [ ] MongoDB chat + notifications feed; chat UI
- [ ] CQRS-lite: denormalized read model for the runner feed
- [ ] batching (same store + nearby zone + time window) — first to cut if the sprint slips
- **Demo #5:** order 2 items off a canteen menu; runner fronts cash at pickup, ledger repays;
  rating changes matching; live chat.
- **Patterns:** CQRS/materialized view · ledger (append-only money) · polyglot persistence ·
  cache-aside · snapshot vs reference (price at order time)

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
| Verified handoff (OTP/order no.) | Vendor menus + cart UI | Menu photos/uploads |

**Risk peaks:** Sprints 3 & 4. Keep one catch-up day per sprint for Docker/Kafka/integration gremlins.
