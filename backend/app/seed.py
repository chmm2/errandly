"""Seed baseline data: a campus and an approved admin/test user.

Run:  docker compose exec backend python -m app.seed
Idempotent — safe to run repeatedly.
"""

import asyncio

from sqlalchemy import select

from app.core.database import SessionLocal
from app.core.security import hash_password
from app.modules.auth.models import AuthCredential, User
from app.modules.campus.models import Campus

DEFAULT_CAMPUS = "VIT Vellore"
TEST_EMAIL = "test.student@vitstudent.ac.in"
TEST_PASSWORD = "password123"


async def seed() -> None:
    async with SessionLocal() as db:
        campus = await db.scalar(select(Campus).where(Campus.name == DEFAULT_CAMPUS))
        if campus is None:
            campus = Campus(name=DEFAULT_CAMPUS, country="IN", timezone="Asia/Kolkata")
            db.add(campus)
            await db.flush()
            print(f"created campus: {campus.name}")

        user = await db.scalar(select(User).where(User.email == TEST_EMAIL))
        if user is None:
            user = User(
                campus_id=campus.id,
                student_id="23BCE0001",
                email=TEST_EMAIL,
                display_name="Test Student",
                account_status="ACTIVE",  # pre-approved so login works out of the box
            )
            user.credentials = AuthCredential(password_hash=hash_password(TEST_PASSWORD))
            db.add(user)
            print(f"created active test user: {TEST_EMAIL} / {TEST_PASSWORD}")

        await db.commit()
        print("seed complete.")


if __name__ == "__main__":
    asyncio.run(seed())
