import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, update

from app.core.database import SessionLocal
from app.core.redis import redis_client
from app.main import app
from app.modules.auth.models import User
from app.modules.campus.models import Campus
from app.modules.ledger import service as ledger_service

# Every test user starts funded so escrow holds (required to post any errand)
# succeed without each test wiring up a top-up.
TEST_WALLET = 100000.0


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
                "student_id": f"23BCE{uuid.uuid4().hex[:5]}",
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
            u = await db.get(User, user_id)
            await ledger_service.credit_topup(db, u.campus_id, user_id, TEST_WALLET)
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
