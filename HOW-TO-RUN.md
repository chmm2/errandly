# How to run Errandly

Two things need to be running at once: the **backend stack** (Docker — API + Postgres +
Redis) and the **frontend** (Vite dev server). Use two separate terminal windows/tabs.

## First time only

```
docker compose up -d --build
docker compose exec backend alembic upgrade head
docker compose exec backend python -m app.seed        # creates a campus + test user
cd frontend
npm install
```

Test login after seeding: `test.student@vitstudent.ac.in` / `password123`

## Every time — Terminal 1 (backend)

```
docker compose up -d
```

That's it — starts the API (port 8000), Postgres (port 5433), and Redis (port 6379) in the
background. Check it's healthy:

```
docker compose ps
curl http://localhost:8000/health
```

Stop it with `docker compose down` (data is kept). Watch logs with `docker compose logs -f backend`.

## Every time — Terminal 2 (frontend)

```
cd frontend
npm run dev
```

Opens on **http://localhost:5173** — that's the URL to open in your browser, not :8000.

> **Port clash?** If localhost:5173 shows a *different* app, another project on your machine
> owns that port — Vite will then start Errandly on the next free port. **Read the terminal
> output** for the actual URL (e.g. `Local: http://localhost:5174/`), or run
> `npx vite --port 5180` to pick one explicitly. Same idea as our Postgres living on 5433.

## After pulling new code (`git pull`)

| What changed | What to run |
|---|---|
| Just app code | nothing — both servers hot-reload |
| A new file in `backend/alembic/versions/` | `docker compose exec backend alembic upgrade head` |
| `backend/pyproject.toml` (new dependency) | `docker compose up -d --build` |
| `frontend/package.json` (new dependency) | `cd frontend && npm install` |

If unsure, running the migration + rebuild command is always safe — it never deletes data.

## Useful extras

### Tests

The suite runs against its **own** database, `errandly_test`, created and
migrated automatically on first run. It never touches the app database, so it
is safe to run while somebody is demoing. To start from a clean schema:

```
docker compose exec db dropdb -U errandly errandly_test
```

The next `pytest` recreates and migrates it.

```
docker compose exec backend pytest -q          # run backend tests
docker compose exec backend ruff check .        # lint backend
docker compose exec backend alembic upgrade head  # apply new migrations
docker compose logs -f backend                  # tail backend logs
docker compose down                             # stop everything (keeps data)
docker compose down -v                          # stop AND wipe the database (careful)
```

**API docs (Swagger):** http://localhost:8000/docs
**Database GUI:** pgAdmin → host `localhost`, port `5433`, db/user/password all `errandly`
