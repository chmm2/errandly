"""Seed the full demo cast: campus, two students, an admin, a vendor with a
real menu, and campus reference prices — so a fresh clone is demoable
immediately.

Run:  docker compose exec backend python -m app.seed
Idempotent — safe to run repeatedly.

Accounts created (all pre-approved):
  student  test.student@vitstudent.ac.in   / password123
  student  priya.runner@vitstudent.ac.in   / password123
  admin    admin@vitstudent.ac.in          / password123
  vendor   foodys@errandlyvendors.in       / vendorpass123   (Foodys Express)

The cast, vendor and menu come from the shared dev seed; this branch adds the
campus reference prices and the starting wallet balances that escrow needs.
"""

import asyncio
from decimal import Decimal

from sqlalchemy import select

import app.models  # noqa: F401 — register ALL mappers; the ledger FKs reach errands
from app.core.database import SessionLocal
from app.core.security import hash_password
from app.modules.auth.models import AuthCredential, User
from app.modules.campus.models import Campus
from app.modules.fraud.models import ReferencePrice
from app.modules.fraud.normalize import normalize
from app.modules.ledger import service as ledger
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

# Non-MRP items a runner might front cash for. Bands are deliberately generous:
# an admin widening a band later is routine, but a band set too tight flags
# honest runners on day one, and that is the expensive mistake.
#   (display name, typical, band min, band max)
REFERENCE_PRICES = [
    ("Chicken Puff", 20, 15, 30),
    ("Veg Puff", 15, 10, 25),
    ("Masala Tea", 10, 6, 18),
    ("Samosa", 15, 10, 25),
    ("Veg Sandwich", 35, 25, 50),
    ("Cold Coffee", 40, 30, 60),
]

# Rupees over the reference before a claim is flagged outright. One flat
# number across every item, so a runner at a counter can hold it in their head.
THRESHOLD_RUPEES = 20

# Every student starts with wallet credit — orders escrow money up front, so a
# demo account with an empty wallet cannot place a single errand.
STARTING_BALANCE = Decimal("1000")


async def _ensure_user(
    db, campus_id, *, email, name, role="STUDENT", student_id=None, password=PASSWORD
) -> User:
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

        students = [
            await _ensure_user(db, campus.id, email=email, name=name, student_id=sid)
            for sid, email, name in STUDENTS
        ]

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

        created = 0
        for display_name, price, lo, hi in REFERENCE_PRICES:
            item_key = normalize(display_name)
            existing = await db.scalar(
                select(ReferencePrice).where(
                    ReferencePrice.campus_id == campus.id,
                    ReferencePrice.item_key == item_key,
                )
            )
            if existing is None:
                db.add(
                    ReferencePrice(
                        campus_id=campus.id,
                        item_key=item_key,
                        display_name=display_name,
                        reference_price=Decimal(price),
                        band_min=Decimal(lo),
                        band_max=Decimal(hi),
                        tolerance_abs=Decimal(THRESHOLD_RUPEES),
                        source="ADMIN",
                    )
                )
                created += 1
        if created:
            print(f"created {created} campus reference price(s)")

        # Top up only wallets that are empty, so re-running the seed never
        # quietly inflates a balance you were using to test a spend.
        for student in students:
            if await ledger.balance(db, student.id) <= 0:
                await ledger.topup(db, student.id, STARTING_BALANCE, memo="Demo credit")
                print(f"funded {student.email} with ₹{STARTING_BALANCE}")

        await db.commit()
        print("seed complete.")


if __name__ == "__main__":
    asyncio.run(seed())
