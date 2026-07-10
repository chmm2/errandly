# Errandly — Delivery Roadmap

3 people · 2-week sprints · ~15-week semester. Tick boxes as you finish. Protect the **Must-have** column;
if a sprint slips, cut from **Could-have**, never from **Must-have**.

**Roles (primary owner; everyone reviews):** Chris = backend/services · Ujjwal = frontend/UX · Dhanjith = infra/data.
**Definition of Done:** merged to main · tests green in CI · runs in `docker compose up` · demoable · README updated.

---

## Sprint 0 — Foundations (Week 1)
- [x] Repo, structure, .gitignore, README, ROADMAP
- [ ] Docker Compose (Postgres+PostGIS, Redis) + backend Dockerfile
- [ ] FastAPI skeleton + health endpoint
- [ ] SQLAlchemy async + Alembic wired
- [ ] GitHub Actions CI (lint + test)
- **Demo:** `docker compose up` runs; CI green.

## Sprint 1 — Auth & walking skeleton (Weeks 2–3)
- [ ] users / auth_credentials / refresh_tokens models + migration
- [ ] register / login / refresh endpoints + JWT + argon2
- [ ] role/capability guard; Redis JWT blacklist
- [ ] React shell: login/register, protected routes, bare order form
- [ ] Seed script (campus, zones, store, test users)
- **Demo #1:** login → create order → mark delivered (skeleton).

## Sprint 2 — Order core & lifecycle (Weeks 4–5)
- [ ] orders / order_items / order_events + state machine (guarded transitions)
- [ ] optimistic locking (version); cancel-before-pickup
- [ ] customer order flow UI + status + history
- [ ] integration tests for every transition (incl. illegal)
- **Demo #2:** full lifecycle from UI with audit trail.

## Sprint 3 — Geo, matching & live tracking (Weeks 6–7)  ⚠ risk peak
- [ ] runner_profiles / runner_status; availability toggle
- [ ] matching engine (Redis GEOSEARCH, score by proximity+load+direction)
- [ ] offer → accept/timeout → broaden retry loop; load cap
- [ ] browser Geolocation capture; runner dashboard
- [ ] WebSocket live order status
- **Demo #3:** order → nearest runner live push → accept → live tracking.

## Sprint 4 — Kafka backbone & timetable (Weeks 8–9)  ⚠ risk peak
- [ ] emit ORDER_* events to Kafka
- [ ] extract Notification + Analytics as idempotent consumers
- [ ] timetable_slots (overlap-exclusion) + enforcer job (auto-block runners)
- [ ] timetable UI, notifications panel, basic analytics
- **Demo #4:** one event fans out to 2 services; runner auto-blocks during class.

## Sprint 5 — Batching, trust, chat, payments (Weeks 10–11)
- [ ] batching (same store + nearby zone + time window) + delivery sequence
- [ ] ledger_entries / wallets; settlement on delivery (KARMA now, UPI later)
- [ ] ratings → reputation → feedback into matching
- [ ] MongoDB chat + notifications feed; chat UI
- **Demo #5:** batched delivery; rating changes matching; live chat.

## Sprint 6 — Admin, security, observability (Weeks 12–13)
- [ ] disputes workflow; admin suspend/ban → Redis blacklist
- [ ] rate limiting; SQLi/XSS/CSRF audit
- [ ] admin dashboard + config panel
- [ ] Prometheus + Grafana (latency, Kafka lag, Redis hits); audit logs; backups
- **Demo #6:** admin suspends user (instant block); Grafana live; dispute resolved.

## Sprint 7 — Integration, testing, docs, demo (Weeks 14–15)
- [ ] end-to-end integration + load test (1000 concurrent)
- [ ] team bug bash; fix critical/high; security pass
- [ ] docs (architecture, API, deploy), README, demo script + rehearsal
- [ ] viva prep (each person explains their seam); backup demo video
- **Demo #7 (final):** happy path + 2 edge cases + architecture walkthrough.

---

## MoSCoW — what's droppable
| Must-have (never cut) | Should-have | Could-have (cut first) |
|---|---|---|
| Auth + verification | Timetable block | Batching / route opt |
| Order lifecycle + audit | Ratings/reputation | MongoDB chat |
| Runner matching + geo | Kafka async split | gRPC internal call |
| Live tracking | Payment ledger | Full Prometheus/Grafana |
| Admin suspend/ban | Disputes | Multi-campus UI |

**Risk peaks:** Sprints 3 & 4. Keep one catch-up day per sprint for Docker/Kafka/integration gremlins.
