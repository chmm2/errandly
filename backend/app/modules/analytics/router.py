from datetime import date, timedelta

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.modules.analytics.models import DailyStat
from app.modules.auth.dependencies import require_active_user
from app.modules.auth.models import User

router = APIRouter(prefix="/analytics", tags=["analytics"])


class AnalyticsSummary(BaseModel):
    days: int
    orders_created: int
    orders_completed: int
    orders_cancelled: int
    reward_total: float


@router.get("/summary", response_model=AnalyticsSummary)
async def summary(
    days: int = 7,
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Campus totals over the last N days, straight from the consumer-built
    read model (no scans over the errands table)."""
    days = max(1, min(days, 90))
    since = date.today() - timedelta(days=days - 1)
    row = (
        await db.execute(
            select(
                func.coalesce(func.sum(DailyStat.orders_created), 0),
                func.coalesce(func.sum(DailyStat.orders_completed), 0),
                func.coalesce(func.sum(DailyStat.orders_cancelled), 0),
                func.coalesce(func.sum(DailyStat.reward_total), 0),
            ).where(DailyStat.campus_id == user.campus_id, DailyStat.stat_date >= since)
        )
    ).one()
    return AnalyticsSummary(
        days=days,
        orders_created=row[0],
        orders_completed=row[1],
        orders_cancelled=row[2],
        reward_total=float(row[3]),
    )
