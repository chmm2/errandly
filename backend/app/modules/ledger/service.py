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

import logging
import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import case, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.modules.auth.models import User
from app.modules.ledger.models import ENTRY_DIRECTION, EscrowHold, LedgerEntry

logger = logging.getLogger(__name__)

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
    buffer_pct: float | None = None,
    buffer_base: Decimal | None = None,
) -> EscrowHold:
    """Move the requester's money into escrow at order time.

    Held up front so a runner who fronts cash at the counter is not trusting the
    requester to still have funds an hour later. The hold is the runner's
    guarantee of payment.

    The hold carries headroom, but only over `buffer_base`:

        hold = spend_estimate + buffer_base x buffer_pct + reward

    Shop prices move, and the runner discovers that at the counter with their
    own cash already spent. Without headroom a requester who budgeted exactly
    could not cover a ₹25 difference, and the person out of pocket would be the
    runner. Whatever the buffer is not needed for goes straight back at
    settlement, so the cost to the requester is temporary and visible.

    `buffer_base` is the NON-MRP part of the order - loose-priced goods whose
    real cost is discovered at the counter. An MRP item carries its price
    printed on the packet, so there is nothing to discover and nothing to pad;
    holding extra against it would lock money no outcome could ever need. Cash
    stated for a gate or parcel pickup is exact for the same reason. Callers
    that pass nothing get no headroom at all, which is the safe default: money
    is only ever tied up when a caller can say why.
    """
    items_total = _money(items_total)
    reward = _money(reward)
    collect_amount = _money(collect_amount)

    # What the runner is expected to spend at the counter. Catalogue orders
    # carry it as priced items; gate and parcel pickups carry it as the cash
    # the requester says will change hands.
    if buffer_pct is None:
        buffer_pct = getattr(settings, "escrow_buffer_pct", 0.0)
    spend_estimate = _money(items_total + collect_amount)

    # Only the uncertain part is padded. Clamped to the estimate so a caller
    # cannot pad more than the order is worth, and floored at zero so a bad
    # value cannot subtract from the hold.
    base = _money(buffer_base or 0)
    base = max(Decimal("0"), min(base, spend_estimate))
    buffer = _money(base * Decimal(str(buffer_pct)))

    # The fee is deliberately outside the base. It is fixed and known, so
    # padding it would lock money that could never be needed - the requester
    # would simply have less to spend for no protection in return.
    total = _money(spend_estimate + buffer + reward)

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
        buffer_base=base,
        items_total=items_total,
        reward=reward,
        collect_amount=collect_amount,
        buffer=buffer,
        amount=total,
    )
    db.add(hold)
    await db.flush()
    return hold


async def estimated_spend(db: AsyncSession, errand_id: uuid.UUID) -> Decimal:
    """What the runner was expected to spend, as recorded when money was held.

    The hold is the authoritative record of the estimate - it is what the
    requester's wallet was actually charged against, and unlike the errand row
    it cannot drift afterwards. Excludes the fee and the buffer: this is the
    outlay, not the ceiling.
    """
    hold = await db.get(EscrowHold, errand_id)
    if hold is None:
        return Decimal("0")
    return _money(_money(hold.items_total) + _money(hold.collect_amount))


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
    remaining = _money(hold.amount) - _money(hold.released_amount)

    # The fee is ring-fenced. A runner who overspends past the buffer has a
    # problem with the reimbursement, not with being paid for the work, and
    # silently eating their fee to cover the gap would punish them for a shop
    # putting its prices up.
    reward = min(reward, max(Decimal("0"), remaining))
    room = max(Decimal("0"), remaining - reward)

    # Cap rather than raise. Settlement runs on a Kafka consumer: raising here
    # fails the event, which is redelivered, which fails again - an unpayable
    # errand would retry forever and block the partition. Paying what is held
    # and recording the gap is recoverable; a stuck consumer is not.
    shortfall = max(Decimal("0"), reimbursement - room)
    reimbursement = min(reimbursement, room)
    payout = _money(reward + reimbursement)

    if shortfall > 0:
        logger.warning(
            "errand %s: runner spent ₹%s more than was held; paying the held "
            "amount and leaving the difference for an admin",
            errand_id,
            shortfall,
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


async def remaining_hold(db: AsyncSession, errand_id: uuid.UUID) -> Decimal:
    """What is still locked against this errand, and therefore payable.

    This is the hard ceiling on the whole settlement. The requester agreed to
    lock exactly this much and no more; anything past it is money the platform
    does not have and never asked them for.
    """
    hold = await db.get(EscrowHold, errand_id)
    if hold is None:
        return Decimal("0")
    return max(Decimal("0"), _money(hold.amount) - _money(hold.released_amount))


async def block_settlement(
    db: AsyncSession, *, errand_id: uuid.UUID
) -> EscrowHold | None:
    """Freeze a hold instead of settling it, pending an admin decision.

    Used when what the runner is owed exceeds what the requester has locked.
    Neither automatic outcome is acceptable there: paying in full would charge
    the requester money they never agreed to lock, and paying the capped amount
    would silently make the runner absorb a difference that might be a shop's
    price rise or might be an inflated claim. This code cannot tell which, so
    it moves nothing and says so.

    NOT settled_at - the hold is frozen, not finished. Status PENDING_REVIEW
    keeps the full amount inside the requester's held partition, so the money
    stays visibly theirs until someone decides where it goes.
    """
    hold = await _locked_hold(db, errand_id)
    if hold is None:
        raise LedgerError("No escrow hold for this errand.", 404)
    if hold.status in ("RELEASED", "REFUNDED"):
        return hold

    hold.status = "PENDING_REVIEW"
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
