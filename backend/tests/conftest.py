import os
import subprocess
import sys
import uuid
from decimal import Decimal
from urllib.parse import urlsplit, urlunsplit

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, update

from app.core.config import settings

# Tests never send real email.
#
# Registration is the first step of most flows here, so a suite run against a
# configured SMTP server sends a mail per user created - hundreds across a full
# run. That is slow, it delivers to real inboxes, and it eventually fails
# outright: a run on this project hit Gmail's daily sending cap and took seven
# otherwise-passing tests down with a 550, in files that have nothing to do
# with email.
#
# Blanking the host puts the app in its own dev mode, where the OTP comes back
# on the X-Dev-OTP header instead. That is what the verification tests already
# assert against, so this also fixes three failures that had been carried as
# "known" for exactly this reason.
settings.smtp_host = ""

# Exploration is a coin flip taken inside dispatch, so leaving it on would make
# every test that asserts anything about offer ordering fail a few percent of
# the time — the worst kind of failure, since it looks like a real regression
# and passes on re-run. Tests that need exploration turn it on explicitly.
settings.offer_explore_rate = 0.0

# The suite gets its own database, always.
#
# These imports used to pull in the app's own engine bound to DATABASE_URL,
# which in practice meant the shared development database. Every run left its
# fixtures behind in it: hundreds of `user_*` accounts, a "Test Campus", and
# vendors called "Store A" and "Test Canteen", all of them visible to anyone
# using the real app. The `campus` fixture at the bottom of this file picks the
# FIRST campus it finds, so once "Test Campus" existed, real accounts could be
# created onto it and see an entirely different set of shops from everybody
# else - which is exactly what happened.
#
# The name is derived rather than configured: whatever DATABASE_URL says, the
# suite appends _test and uses that. There is deliberately no way to point this
# at the shared database by editing an env file, because the failure is silent
# and only shows up later as junk data in somebody's demo.
def _derive_test_url(url: str) -> str:
    parts = urlsplit(url)
    return urlunsplit(parts._replace(path=f"/{parts.path.lstrip('/')}_test"))


TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL") or _derive_test_url(
    settings.database_url
)
if TEST_DATABASE_URL == settings.database_url:
    raise RuntimeError(
        "The test database URL matches the application one. Refusing to run: "
        "the suite writes hundreds of throwaway users and would corrupt it."
    )

settings.database_url = TEST_DATABASE_URL
# Alembic runs in a subprocess (its env.py calls asyncio.run, which cannot be
# nested inside the already-running test loop), so the override has to travel
# through the environment as well as through `settings`.
os.environ["DATABASE_URL"] = TEST_DATABASE_URL

from app.core.database import SessionLocal
from app.core.redis import redis_client
from app.main import app
from app.modules.auth.models import User
from app.modules.campus.models import Campus
from app.modules.ledger import service as ledger


@pytest.fixture(scope="session", autouse=True)
async def _test_database():
    """Create the test database if it is missing, then migrate it to head.

    Session-scoped and autouse so it runs before any fixture touches the
    engine. The database is kept between runs rather than dropped: migrating
    from zero costs far more than the suite itself, and the tests are already
    written to tolerate accumulated rows. Drop it by hand to start clean:

        docker compose exec db dropdb -U errandly errandly_test
    """
    import asyncpg

    parts = urlsplit(TEST_DATABASE_URL)
    db_name = parts.path.lstrip("/")

    # asyncpg speaks plain postgresql://, not SQLAlchemy's +asyncpg dialect,
    # and CREATE DATABASE cannot run inside the target database itself.
    admin_dsn = urlunsplit(
        parts._replace(scheme="postgresql", path="/postgres")
    )
    conn = await asyncpg.connect(admin_dsn)
    try:
        exists = await conn.fetchval(
            "SELECT 1 FROM pg_database WHERE datname = $1", db_name
        )
        if not exists:
            # Identifier, so it cannot be parameterised. It is derived from our
            # own DATABASE_URL rather than user input, and quoting keeps a name
            # with a hyphen or capital in it valid.
            await conn.execute(f'CREATE DATABASE "{db_name}"')
    finally:
        await conn.close()

    # A subprocess, because alembic/env.py ends in asyncio.run() and this
    # fixture is already inside a running loop. It reads DATABASE_URL, which
    # was pointed at the test database above.
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"Could not migrate the test database:\n{result.stdout}\n{result.stderr}"
        )
    yield


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture(autouse=True)
async def flush_redis_state():
    """All test requests share one client IP and one Redis, so clear
    rate-limit windows and geo/throttle state between tests."""
    for pattern in ("rl:*", "runners:geo:*", "runner:locwrite:*"):
        keys = await redis_client.keys(pattern)
        if keys:
            await redis_client.delete(*keys)
    yield


@pytest.fixture
def make_user(client, campus):
    """Factory: register + activate + login a fresh user.

    Returns (user_id, auth_headers)."""

    async def _make(name: str = "Test User") -> tuple[uuid.UUID, dict[str, str]]:
        email = f"user_{uuid.uuid4().hex[:10]}@vitstudent.ac.in"
        reg = await client.post(
            "/auth/register",
            json={
                # Full hex, not a 5-character slice. The suite shares one
                # persistent database, so ids accumulate across runs: at a few
                # thousand users a 5-hex tail collides often enough to fail a
                # random fixture most runs, which reads as a flaky test rather
                # than as the birthday problem it is. student_id allows 50.
                "student_id": f"23BCE{uuid.uuid4().hex}",
                "email": email,
                "display_name": name,
                "password": "password123",
            },
        )
        assert reg.status_code == 201, reg.text
        user_id = uuid.UUID(reg.json()["id"])
        async with SessionLocal() as db:
            await db.execute(
                update(User).where(User.id == user_id).values(account_status="ACTIVE")
            )
            await db.commit()
        # Every order now escrows the requester's money up front, so a test
        # user with an empty wallet cannot place one. Fund generously - no test
        # here is about running out of money, and the ones that are top up
        # their own way.
        async with SessionLocal() as db:
            await ledger.topup(db, user_id, Decimal("100000"), memo="Test funding")
            await db.commit()
        login = await client.post(
            "/auth/login", json={"email": email, "password": "password123"}
        )
        assert login.status_code == 200, login.text
        token = login.json()["access_token"]
        return user_id, {"Authorization": f"Bearer {token}"}

    return _make


@pytest.fixture
async def campus():
    """Ensure a default campus exists for registration."""
    async with SessionLocal() as db:
        c = await db.scalar(select(Campus).limit(1))
        if c is None:
            c = Campus(name="Test Campus")
            db.add(c)
            await db.commit()
            await db.refresh(c)
        return c.id
