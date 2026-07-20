from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.modules.auth.dependencies import require_active_user, require_admin
from app.modules.auth.models import User
from app.modules.ledger import service
from app.modules.ledger.models import LedgerEntry
from app.modules.ledger.schemas import (
    EarningsSummary,
    QuoteOut,
    QuoteRequest,
    TopupRequest,
    VerifyOut,
    WalletOut,
)
from app.modules.ledger.service import LedgerError

router = APIRouter(prefix="/ledger", tags=["ledger"])

EARNING_TYPES = ("REWARD", "REIMBURSEMENT")


def _raise(e: LedgerError) -> None:
    raise HTTPException(e.status_code, e.message) from e


@router.get("/me", response_model=EarningsSummary)
async def my_earnings(
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Runner earnings card. Balance is the net wallet (derived by SUM); the
    week figures count only payout entries (REWARD/REIMBURSEMENT)."""
    balance = await service.account_balance(db, user.campus_id, user.id)
    week_ago = datetime.now(UTC) - timedelta(days=7)
    row = (
        await db.execute(
            select(
                func.coalesce(func.sum(LedgerEntry.amount), 0),
                func.count(func.distinct(LedgerEntry.errand_id)),
            ).where(
                LedgerEntry.account_id == user.id,
                LedgerEntry.campus_id == user.campus_id,
                LedgerEntry.entry_type.in_(EARNING_TYPES),
                LedgerEntry.created_at >= week_ago,
            )
        )
    ).one()
    return EarningsSummary(balance=balance, week_total=float(row[0]), week_runs=row[1])


@router.get("/wallet", response_model=WalletOut)
async def wallet(
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_db),
):
    summary = await service.wallet_summary(db, user.campus_id, user.id)
    return WalletOut(**summary)


@router.post("/wallet/topup", response_model=WalletOut)
async def topup(
    body: TopupRequest,
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Add money to the wallet via the configured payment provider (simulated
    in dev — credits instantly, no real money moves)."""
    try:
        await service.topup(db, user.campus_id, user.id, body.amount)
    except LedgerError as e:
        _raise(e)
    summary = await service.wallet_summary(db, user.campus_id, user.id)
    return WalletOut(**summary)


@router.post("/quote", response_model=QuoteOut)
async def quote(
    body: QuoteRequest,
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Fee breakdown for the checkout screen — does not hold anything."""
    q = await service.quote(
        db, user.campus_id, body.drop_lat, body.drop_lng, body.item_total, body.tip
    )
    return QuoteOut(**q)


@router.get("/verify", response_model=VerifyOut)
async def verify(
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Recompute the campus ledger's hash chain and report tampering. Admin
    only — this is the integrity auditor."""
    return VerifyOut(**await service.verify_chain(db, user.campus_id))
