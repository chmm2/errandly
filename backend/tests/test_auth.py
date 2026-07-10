import uuid

import pytest
from sqlalchemy import update

from app.core.database import SessionLocal
from app.modules.auth.models import User

# Run all tests in this module on the shared session-scoped event loop so the
# module-level async engine's pooled connections survive across tests.
pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_health(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["checks"]["db"] == "up"


async def test_register_login_me_flow(client, campus):
    email = f"user_{uuid.uuid4().hex[:8]}@vitstudent.ac.in"
    student_id = f"23BCE{uuid.uuid4().hex[:4]}"

    # Register — new users start PENDING
    reg = await client.post(
        "/auth/register",
        json={
            "student_id": student_id,
            "email": email,
            "display_name": "Flow Test",
            "password": "password123",
        },
    )
    assert reg.status_code == 201, reg.text
    assert reg.json()["account_status"] == "PENDING"

    # PENDING users cannot log in yet
    denied = await client.post("/auth/login", json={"email": email, "password": "password123"})
    assert denied.status_code == 403

    # Admin approves
    async with SessionLocal() as db:
        await db.execute(update(User).where(User.email == email).values(account_status="ACTIVE"))
        await db.commit()

    # Now login works
    login = await client.post("/auth/login", json={"email": email, "password": "password123"})
    assert login.status_code == 200, login.text
    tokens = login.json()
    assert tokens["access_token"] and tokens["refresh_token"]

    # /me with the access token
    me = await client.get("/auth/me", headers={"Authorization": f"Bearer {tokens['access_token']}"})
    assert me.status_code == 200
    assert me.json()["email"] == email

    # Wrong password is rejected
    bad = await client.post("/auth/login", json={"email": email, "password": "wrongpass"})
    assert bad.status_code == 401


async def test_refresh_rotation(client, campus):
    email = f"user_{uuid.uuid4().hex[:8]}@vitstudent.ac.in"
    await client.post(
        "/auth/register",
        json={
            "student_id": f"23BCE{uuid.uuid4().hex[:4]}",
            "email": email,
            "display_name": "Refresh Test",
            "password": "password123",
        },
    )
    async with SessionLocal() as db:
        await db.execute(update(User).where(User.email == email).values(account_status="ACTIVE"))
        await db.commit()

    tokens = (
        await client.post("/auth/login", json={"email": email, "password": "password123"})
    ).json()

    refreshed = await client.post("/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert refreshed.status_code == 200

    # Old refresh token is single-use — reuse must fail
    reused = await client.post("/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert reused.status_code == 401
