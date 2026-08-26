import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.modules.auth.dependencies import require_active_user
from app.modules.auth.models import User
from app.modules.errands.models import Errand
from app.modules.ledger import service as ledger
from app.modules.ledger.models import EscrowHold, LedgerEntry
from app.modules.ledger.schemas import (
    EarningsSummary,
    EscrowOut,
    LedgerEntryOut,
    TopUpRequest,
    WalletOut,
)

router = APIRouter(prefix="/ledger", tags=["ledger"])

RECENT_ENTRY_LIMIT = 25


@router.get("/me", response_model=EarningsSummary)
async def my_earnings(
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Derived, never stored: every number is a sum over the append-only log."""
    balance = await ledger.balance(db, user.id)
    week_ago = datetime.now(UTC) - timedelta(days=7)
    row = (
        await db.execute(
            select(
                func.coalesce(
                    func.sum(
                        case(
                            (LedgerEntry.direction == "CREDIT", LedgerEntry.amount),
                            else_=-LedgerEntry.amount,
                        )
                    ),
                    0,
                ),
                func.count(func.distinct(LedgerEntry.errand_id)),
            ).where(
                LedgerEntry.user_id == user.id,
                LedgerEntry.created_at >= week_ago,
                # Earnings means money earned running, not money topped up.
                LedgerEntry.entry_type.in_(("REWARD", "REIMBURSEMENT")),
            )
        )
    ).one()
    return EarningsSummary(
        balance=float(balance), week_total=float(row[0]), week_runs=row[1]
    )


@router.get("/me/wallet", response_model=WalletOut)
async def my_wallet(
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_db),
):
    balance = await ledger.balance(db, user.id)
    held = await db.scalar(
        select(
            func.coalesce(func.sum(EscrowHold.amount - EscrowHold.released_amount), 0)
        ).where(
            EscrowHold.requester_id == user.id,
            EscrowHold.status.in_(("HELD", "PENDING_REVIEW")),
        )
    )
    rows = await db.execute(
        select(LedgerEntry)
        .where(LedgerEntry.user_id == user.id)
        .order_by(LedgerEntry.created_at.desc())
        .limit(RECENT_ENTRY_LIMIT)
    )
    return WalletOut(
        balance=float(balance),
        held=float(held or 0),
        recent=[LedgerEntryOut.model_validate(e) for e in rows.scalars()],
    )


@router.post("/me/topup", response_model=WalletOut)
async def top_up(
    data: TopUpRequest,
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Self-serve top-up, development only.

    Gated on environment on purpose: in production this endpoint must not
    exist, because a wallet you can credit yourself is not a wallet. The
    production door is a verified payment-gateway callback, and it is the
    only other caller of ledger.topup().
    """
    if settings.environment not in ("development", "test"):
        raise HTTPException(404, "Not found.")
    try:
        await ledger.topup(db, user.id, Decimal(str(data.amount)), memo="Demo top-up")
    except ledger.LedgerError as e:
        raise HTTPException(e.status_code, e.message) from e
    await db.commit()
    return await my_wallet(user=user, db=db)


@router.get("/errands/{errand_id}/escrow", response_model=EscrowOut)
async def errand_escrow(
    errand_id: uuid.UUID,
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_db),
):
    """The receipt for one order. Visible to the two parties and admins only."""
    hold = await db.get(EscrowHold, errand_id)
    if hold is None:
        raise HTTPException(404, "No escrow hold for this errand.")
    errand = await db.get(Errand, errand_id)
    allowed = {hold.requester_id}
    if errand and errand.runner_id:
        allowed.add(errand.runner_id)
    if user.id not in allowed and user.role != "ADMIN":
        raise HTTPException(403, "Not your order.")
    return EscrowOut.model_validate(hold)
