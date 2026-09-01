import asyncio
from decimal import Decimal
from sqlalchemy import select
import app.modules.errands.models  # noqa: F401  (mapper registry)
from app.core.database import SessionLocal
from app.modules.auth.models import User
from app.modules.ledger import service as ledger

TARGET = Decimal("1000.00")
EMAILS = ["test.student@vitstudent.ac.in", "priya.runner@vitstudent.ac.in"]

async def main():
    async with SessionLocal() as db:
        for email in EMAILS:
            u = await db.scalar(select(User).where(User.email == email))
            cur = await ledger.balance(db, u.id)
            if cur < TARGET:
                await ledger.topup(db, u.id, TARGET - cur, memo="Demo reset")
            elif cur > TARGET:
                await ledger.clawback(db, user_id=u.id, amount=cur - TARGET, memo="Demo reset")
            await db.commit()
            print(f"  {email}: {cur} -> {await ledger.balance(db, u.id)}")

asyncio.run(main())
