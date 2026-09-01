import uuid
from decimal import Decimal

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

from app.core.database import SessionLocal
from app.core.redis import redis_client
from app.main import app
from app.modules.auth.models import User
from app.modules.campus.models import Campus
from app.modules.ledger import service as ledger


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
