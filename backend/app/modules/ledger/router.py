from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.modules.auth.dependencies import require_active_user
from app.modules.auth.models import User
from app.modules.ledger.models import LedgerEntry

router = APIRouter(prefix="/ledger", tags=["ledger"])


class EarningsSummary(BaseModel):
    balance: float
    week_total: float
    week_runs: int


@router.get("/me", response_model=EarningsSummary)
async def my_earnings(
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Derived, never stored: both numbers are sums over the append-only log."""
    balance = (
        await db.scalar(
            select(func.coalesce(func.sum(LedgerEntry.amount), 0)).where(
                LedgerEntry.user_id == user.id
            )
        )
    ) or 0
    week_ago = datetime.now(UTC) - timedelta(days=7)
    row = (
        await db.execute(
            select(
                func.coalesce(func.sum(LedgerEntry.amount), 0),
                func.count(func.distinct(LedgerEntry.errand_id)),
            ).where(LedgerEntry.user_id == user.id, LedgerEntry.created_at >= week_ago)
        )
    ).one()
    return EarningsSummary(
        balance=float(balance), week_total=float(row[0]), week_runs=row[1]
    )
