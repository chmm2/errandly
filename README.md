# Errandly

A secure, student-only **peer-to-peer campus errand & micro-delivery platform**. Students place errand
requests (food, groceries, parcel-point pickups); other verified students ("runners") fulfil them for small
incentives. Campus-restricted, identity-verified, timetable-aware.

## Architecture (target)

Event-driven system that starts as a modular monolith and splits at natural seams.

```
React (TS)  ──HTTPS/WS──►  FastAPI backend  ──►  PostgreSQL + PostGIS   (source of truth)
                                 │            ──►  Redis                 (geo, sessions, cache)
                                 │            ──►  Kafka                 (async event backbone)
                                 │            ──►  MongoDB (later)        (chat, notifications feed)
                        Notification · Analytics · Timetable-enforcer (Kafka consumers / jobs)
```

## Tech stack

| Layer            | Choice                                        |
|------------------|-----------------------------------------------|
| Backend          | FastAPI (async) + Pydantic v2                  |
| ORM / migrations | SQLAlchemy 2.0 (async) + Alembic + GeoAlchemy2 |
| Database         | PostgreSQL 16 + PostGIS                        |
| Cache / geo      | Redis 7                                        |
| Events           | Kafka (added in Sprint 4)                      |
| Auth             | JWT (access + refresh), argon2 hashing         |
| Containers       | Docker + Docker Compose                        |
| Frontend         | React + TypeScript (Sprint 1+)                 |

## Quick start

```bash
cp backend/.env.example backend/.env      # adjust secrets if you like
docker compose up --build                 # starts Postgres, Redis, backend
# backend: http://localhost:8000  ·  docs: http://localhost:8000/docs
```

Run migrations and seed inside the running backend container:

```bash
docker compose exec backend alembic upgrade head
docker compose exec backend python -m app.seed
```

## Repo layout

```
backend/          FastAPI service
  app/
    core/         config, db, redis, security (cross-cutting)
    modules/      feature modules (auth, orders, runner, ...)
  alembic/        database migrations
frontend/         React app (Sprint 1+)
docker-compose.yml
ROADMAP.md        week-by-week sprint plan and checklist
```

See [ROADMAP.md](ROADMAP.md) for the sprint plan.
