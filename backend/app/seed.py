"""Seed the full demo cast: campus, two students, an admin, and a vendor
with a real menu — so a fresh clone is demoable immediately.

Run:  docker compose exec backend python -m app.seed
Idempotent — safe to run repeatedly.

Accounts created (all pre-approved):
  student  test.student@vitstudent.ac.in   / password123
  student  priya.runner@vitstudent.ac.in   / password123
  admin    admin@vitstudent.ac.in          / password123
  vendor   foodys@errandlyvendors.in       / vendorpass123   (Foodys Express)
"""

import asyncio

from sqlalchemy import select

from app.core.database import SessionLocal
from app.core.security import hash_password
from app.modules.auth.models import AuthCredential, User
from app.modules.campus.models import Campus
from app.modules.vendors.models import MenuItem, Vendor

DEFAULT_CAMPUS = "VIT Vellore"
PASSWORD = "password123"

STUDENTS = [
    ("23BCE0001", "test.student@vitstudent.ac.in", "Test Student"),
    ("23BCE0002", "priya.runner@vitstudent.ac.in", "Priya Runner"),
]

MENU = [
    ("Rolls", "Veg Roll", 40),
    ("Rolls", "Paneer Roll", 60),
    ("Maggi", "Classic Maggi", 35),
    ("Maggi", "Cheese Maggi", 50),
    ("Drinks", "Fresh Lime Juice", 25),
    ("Drinks", "Cold Coffee", 40),
]


async def _ensure_user(db, campus_id, *, email, name, role="STUDENT", student_id=None, password=PASSWORD) -> User:
    user = await db.scalar(select(User).where(User.email == email))
    if user is None:
        user = User(
            campus_id=campus_id,
            student_id=student_id,
            email=email,
            display_name=name,
            role=role,
            account_status="ACTIVE",  # pre-approved so login works out of the box
        )
        user.credentials = AuthCredential(password_hash=hash_password(password))
        db.add(user)
        await db.flush()
        print(f"created {role.lower():7s} {email}")
    return user


async def seed() -> None:
    async with SessionLocal() as db:
        campus = await db.scalar(select(Campus).where(Campus.name == DEFAULT_CAMPUS))
        if campus is None:
            campus = Campus(name=DEFAULT_CAMPUS, country="IN", timezone="Asia/Kolkata")
            db.add(campus)
            await db.flush()
            print(f"created campus: {campus.name}")

        for student_id, email, name in STUDENTS:
            await _ensure_user(db, campus.id, email=email, name=name, student_id=student_id)

        await _ensure_user(
            db, campus.id,
            email="admin@vitstudent.ac.in", name="Campus Admin", role="ADMIN",
        )

        owner = await _ensure_user(
            db, campus.id,
            email="foodys@errandlyvendors.in", name="Foodys Owner",
            role="VENDOR", password="vendorpass123",
        )
        vendor = await db.scalar(select(Vendor).where(Vendor.owner_user_id == owner.id))
        if vendor is None:
            vendor = Vendor(
                campus_id=campus.id,
                owner_user_id=owner.id,
                name="Foodys Express",
                category="FOOD",
                description="Rolls, maggi & juice near Main Gate",
                is_open=True,
            )
            db.add(vendor)
            await db.flush()
            for section, name, price in MENU:
                db.add(MenuItem(vendor_id=vendor.id, section=section, name=name, price=price))
            print(f"created vendor: {vendor.name} with {len(MENU)} menu items")

        await db.commit()
        print("seed complete.")


if __name__ == "__main__":
    asyncio.run(seed())
