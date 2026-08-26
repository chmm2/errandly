"""Wallet balances and escrow.

Two rules hold this together, and every function below exists to keep them:

1. **Balances are derived, never stored.** A balance is a SUM over the
   append-only entry log. There is no mutable number to drift, double-spend, or
   corrupt - the worst a bug can do is write a wrong entry, which is visible and
   reversible, rather than silently wrong state.
2. **A payout can never exceed its hold.** Money leaves escrow only through
   `release_hold`, which draws against `escrow_holds.released_amount` under a
   row lock. The platform cannot be made to pay out money it never collected.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import case, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.models import User
from app.modules.ledger.models import ENTRY_DIRECTION, EscrowHold, LedgerEntry

TWO_PLACES = Decimal("0.01")


class LedgerError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def _money(value) -> Decimal:
    return Decimal(str(value or 0)).quantize(TWO_PLACES)


async def balance(db: AsyncSession, user_id: uuid.UUID) -> Decimal:
    """Credits minus debits. The only definition of "how much do I have"."""
    total = await db.scalar(
        select(
            func.coalesce(
                func.sum(
                    case(
                        (LedgerEntry.direction == "CREDIT", LedgerEntry.amount),
                        else_=-LedgerEntry.amount,
                    )
                ),
                0,
            )
        ).where(LedgerEntry.user_id == user_id)
    )
    return _money(total)


async def _write_entry(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    entry_type: str,
    amount: Decimal,
    errand_id: uuid.UUID | None = None,
    memo: str | None = None,
) -> LedgerEntry | None:
    """Append one entry, or return None if this exact entry already exists.

    Idempotency is enforced by the database, not by a read-then-write check -
    a uniqueness violation on (errand_id, user_id, entry_type) is the signal
    that a Kafka redelivery or a double click already paid this out.
    """
    amount = _money(amount)
    if amount <= 0:
        return None
    direction = ENTRY_DIRECTION[entry_type]
    entry = LedgerEntry(
        user_id=user_id,
        errand_id=errand_id,
        entry_type=entry_type,
        direction=direction,
        amount=amount,
        memo=memo,
    )
    # SAVEPOINT, not rollback: a duplicate entry must undo only itself. Rolling
    # back the whole transaction here would silently discard the escrow updates
    # the caller made around this call, and a redelivered settlement would
    # corrupt the hold instead of being a no-op.
    try:
        async with db.begin_nested():
            db.add(entry)
            await db.flush()
    except IntegrityError:
        return None
    return entry


async def topup(
    db: AsyncSession, user_id: uuid.UUID, amount: Decimal, memo: str | None = None
) -> Decimal:
    """Add funds to a wallet.

    KARMA units for now. When real money arrives this is where a verified
    payment-gateway callback lands - and nowhere else, so there is exactly one
    door into the balance.
    """
    amount = _money(amount)
    if amount <= 0:
        raise LedgerError("Top-up amount must be positive.", 422)
    await _write_entry(
        db, user_id=user_id, entry_type="TOPUP", amount=amount, memo=memo or "Wallet top-up"
    )
    return await balance(db, user_id)


async def place_hold(
    db: AsyncSession,
    *,
    errand_id: uuid.UUID,
    requester_id: uuid.UUID,
    items_total: Decimal,
    reward: Decimal,
    collect_amount: Decimal,
) -> EscrowHold:
    """Move the requester's money into escrow at order time.

    Held up front so a runner who fronts cash at the counter is not trusting the
    requester to still have funds an hour later. The hold is the runner's
    guarantee of payment.
    """
    items_total = _money(items_total)
    reward = _money(reward)
    collect_amount = _money(collect_amount)
    total = _money(items_total + reward + collect_amount)

    if total <= 0:
        raise LedgerError("Nothing to hold for this errand.", 422)

    # Lock the wallet owner's row first: balance is a SUM, so a plain
    # check-then-write lets two concurrent orders both see enough money and
    # both spend it. The lock serializes spends against the same wallet.
    await db.execute(
        select(User.id).where(User.id == requester_id).with_for_update()
    )

    available = await balance(db, requester_id)
    if available < total:
        raise LedgerError(
            f"Wallet is short by ₹{_money(total - available)}. "
            f"Top up to place this order.",
            402,
        )

    entry = await _write_entry(
        db,
        user_id=requester_id,
        errand_id=errand_id,
        entry_type="HOLD",
        amount=total,
        memo="Escrow hold for order",
    )
    if entry is None:
        existing = await db.get(EscrowHold, errand_id)
        if existing:
            return existing
        raise LedgerError("Could not place escrow hold.", 409)

    hold = EscrowHold(
        errand_id=errand_id,
        requester_id=requester_id,
        items_total=items_total,
        reward=reward,
        collect_amount=collect_amount,
        amount=total,
    )
    db.add(hold)
    await db.flush()
    return hold


async def _locked_hold(db: AsyncSession, errand_id: uuid.UUID) -> EscrowHold | None:
    """Fetch a hold under a row lock - settlement must not race itself."""
    return await db.scalar(
        select(EscrowHold).where(EscrowHold.errand_id == errand_id).with_for_update()
    )


async def release_hold(
    db: AsyncSession,
    *,
    errand_id: uuid.UUID,
    runner_id: uuid.UUID,
    reward: Decimal,
    reimbursement: Decimal,
    withheld: Decimal = Decimal("0"),
    memo: str | None = None,
) -> EscrowHold:
    """Pay the runner out of escrow and return any surplus to the requester.

    `withheld` is money the fraud check refused to release - it stays in escrow
    and the hold goes PENDING_REVIEW rather than being refunded, because an
    admin may yet decide the runner was honest and release it.
    """
    hold = await _locked_hold(db, errand_id)
    if hold is None:
        raise LedgerError("No escrow hold for this errand.", 404)
    if hold.status in ("RELEASED", "REFUNDED"):
        return hold

    reward = _money(reward)
    reimbursement = _money(reimbursement)
    withheld = _money(withheld)
    payout = _money(reward + reimbursement)
    remaining = _money(hold.amount) - _money(hold.released_amount)

    if payout > remaining:
        raise LedgerError(
            f"Payout ₹{payout} exceeds the ₹{remaining} still held for this errand.",
            409,
        )

    await _write_entry(
        db,
        user_id=runner_id,
        errand_id=errand_id,
        entry_type="REWARD",
        amount=reward,
        memo=memo or "Delivery reward",
    )
    await _write_entry(
        db,
        user_id=runner_id,
        errand_id=errand_id,
        entry_type="REIMBURSEMENT",
        amount=reimbursement,
        memo="Cash fronted at pickup",
    )

    hold.released_amount = _money(_money(hold.released_amount) + payout)
    surplus = _money(hold.amount) - _money(hold.released_amount) - withheld

    if surplus > 0:
        # The requester over-held (quoted more than was actually spent) -
        # give it straight back rather than quietly keeping it.
        await _write_entry(
            db,
            user_id=hold.requester_id,
            errand_id=errand_id,
            entry_type="REFUND",
            amount=surplus,
            memo="Unspent balance returned",
        )
        hold.released_amount = _money(_money(hold.released_amount) + surplus)

    hold.status = "PENDING_REVIEW" if withheld > 0 else "RELEASED"
    hold.settled_at = datetime.now(UTC)
    await db.flush()
    return hold


async def refund_hold(
    db: AsyncSession, *, errand_id: uuid.UUID, memo: str | None = None
) -> EscrowHold | None:
    """Return everything still held to the requester (cancel / expire)."""
    hold = await _locked_hold(db, errand_id)
    if hold is None:
        return None
    if hold.status in ("RELEASED", "REFUNDED"):
        return hold

    remaining = _money(hold.amount) - _money(hold.released_amount)
    if remaining > 0:
        await _write_entry(
            db,
            user_id=hold.requester_id,
            errand_id=errand_id,
            entry_type="REFUND",
            amount=remaining,
            memo=memo or "Order cancelled",
        )
        hold.released_amount = _money(hold.amount)

    hold.status = "REFUNDED"
    hold.settled_at = datetime.now(UTC)
    await db.flush()
    return hold


async def resolve_withheld(
    db: AsyncSession,
    *,
    errand_id: uuid.UUID,
    runner_id: uuid.UUID,
    pay_runner: bool,
    memo: str | None = None,
) -> EscrowHold:
    """Settle a PENDING_REVIEW hold once an admin has judged the claim.

    Either the runner was honest and gets the withheld remainder, or they were
    not and it goes back to the requester. Both paths close the hold.
    """
    hold = await _locked_hold(db, errand_id)
    if hold is None:
        raise LedgerError("No escrow hold for this errand.", 404)
    if hold.status != "PENDING_REVIEW":
        raise LedgerError("This hold is not awaiting review.", 409)

    remaining = _money(hold.amount) - _money(hold.released_amount)
    if remaining > 0:
        if pay_runner:
            await _write_entry(
                db,
                user_id=runner_id,
                errand_id=errand_id,
                entry_type="REVIEW_PAYOUT",
                amount=remaining,
                memo=memo or "Withheld amount released after review",
            )
        else:
            await _write_entry(
                db,
                user_id=hold.requester_id,
                errand_id=errand_id,
                entry_type="REVIEW_REFUND",
                amount=remaining,
                memo=memo or "Overcharge returned after review",
            )
        hold.released_amount = _money(hold.amount)

    hold.status = "RELEASED"
    hold.settled_at = datetime.now(UTC)
    await db.flush()
    return hold


async def clawback(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    amount: Decimal,
    errand_id: uuid.UUID | None = None,
    memo: str | None = None,
) -> Decimal:
    """Debit a runner for an overpayment already released.

    Used when fraud is found after settlement. A balance is allowed to go
    negative here on purpose: writing the debt down is more honest than
    refusing to record it, and the runner cannot place orders while short.
    """
    await _write_entry(
        db,
        user_id=user_id,
        errand_id=errand_id,
        entry_type="CLAWBACK",
        amount=_money(amount),
        memo=memo or "Fraud adjustment",
    )
    return await balance(db, user_id)
