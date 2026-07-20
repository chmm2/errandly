"""Escrow + tamper-evident ledger.

Money invariants:
- Balances are DERIVED: account_balance = SUM(signed amounts). Nothing stores a
  mutable balance, so none can be silently corrupted.
- Every action books a BALANCED PAIR, so the whole ledger sums to zero.
- Appends are serialized per campus under a Postgres advisory lock, keeping the
  hash chain linear. Throughput is traded for tamper-evidence — fine at campus
  scale, and per-campus locking keeps campuses independent.

Who writes when:
- Holds, refunds and top-ups are written SYNCHRONOUSLY inside the caller's
  transaction — a post must atomically succeed-with-hold or fail, so payment
  can't drift from the order.
- Releases (runner payouts) run in the idempotent settlement CONSUMER, keeping
  the effectively-once payout guarantee.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.crypto import ledger_hmac
from app.modules.ledger.models import (
    ESCROW_ACCOUNT,
    EXTERNAL_ACCOUNT,
    PLATFORM_ACCOUNT,
    EscrowHold,
    LedgerEntry,
)

GENESIS_HASH = b"\x00" * 32


class LedgerError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def _fmt(amount: float) -> str:
    """Fixed 2-dp form so the hash is identical on re-verification."""
    return f"{float(amount):.2f}"


def _canonical(
    seq: int,
    campus_id: uuid.UUID,
    account_id: uuid.UUID,
    errand_id: uuid.UUID | None,
    entry_type: str,
    amount: float,
    prev_hash: bytes,
    created_at: datetime,
) -> bytes:
    return (
        f"{seq}|{campus_id}|{account_id}|{errand_id or ''}|{entry_type}|"
        f"{_fmt(amount)}|{prev_hash.hex()}|{created_at.isoformat()}"
    ).encode()


async def _lock_campus(db: AsyncSession, campus_id: uuid.UUID) -> None:
    """Serialize ledger appends within a campus. Transaction-scoped, so it
    releases automatically on commit/rollback; repeated calls in one
    transaction are harmless."""
    await db.execute(
        text("SELECT pg_advisory_xact_lock(hashtext(:k))"),
        {"k": f"ledger:{campus_id}"},
    )


async def append_entry(
    db: AsyncSession,
    campus_id: uuid.UUID,
    account_id: uuid.UUID,
    entry_type: str,
    amount: float,
    errand_id: uuid.UUID | None = None,
) -> LedgerEntry:
    """Append one signed entry to the campus chain. Rides the caller's
    transaction (no commit). Assumes the campus lock is already held."""
    await _lock_campus(db, campus_id)
    last = (
        await db.execute(
            select(LedgerEntry.seq, LedgerEntry.entry_hash)
            .where(LedgerEntry.campus_id == campus_id)
            .order_by(LedgerEntry.seq.desc())
            .limit(1)
        )
    ).first()
    seq = (last.seq + 1) if last else 1
    prev_hash = last.entry_hash if last else GENESIS_HASH
    created_at = datetime.now(UTC)
    entry_hash = ledger_hmac(
        _canonical(seq, campus_id, account_id, errand_id, entry_type, amount, prev_hash, created_at)
    )
    entry = LedgerEntry(
        campus_id=campus_id,
        seq=seq,
        account_id=account_id,
        errand_id=errand_id,
        entry_type=entry_type,
        amount=amount,
        prev_hash=prev_hash,
        entry_hash=entry_hash,
        created_at=created_at,
    )
    db.add(entry)
    await db.flush()  # make this entry visible to the next append's seq read
    return entry


async def account_balance(
    db: AsyncSession, campus_id: uuid.UUID, account_id: uuid.UUID
) -> float:
    total = await db.scalar(
        select(func.coalesce(func.sum(LedgerEntry.amount), 0)).where(
            LedgerEntry.campus_id == campus_id, LedgerEntry.account_id == account_id
        )
    )
    return float(total or 0)


# ------------------------------------------------------------------------ fees

def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


async def _drop_distance_km(
    db: AsyncSession, campus_id: uuid.UUID, lat: float, lng: float
) -> float:
    """Distance from the campus reference point to the drop. Pickup has no
    coordinates today, so the campus centre is the anchor; if it's unset the
    fee falls back to the base rate (distance 0)."""
    meters = await db.scalar(
        text(
            "SELECT ST_Distance(c.center, "
            "ST_SetSRID(ST_MakePoint(:lng, :lat), 4326)::geography) "
            "FROM campuses c WHERE c.id = :cid AND c.center IS NOT NULL"
        ),
        {"lng": lng, "lat": lat, "cid": str(campus_id)},
    )
    return float(meters or 0) / 1000.0


async def compute_fees(
    db: AsyncSession, campus_id: uuid.UUID, lat: float, lng: float, item_total: float
) -> tuple[float, float, float]:
    """Returns (runner_fee, convenience_fee, total). Distance-based runner fee,
    percentage convenience charge with a floor."""
    km = await _drop_distance_km(db, campus_id, lat, lng)
    runner_fee = round(
        _clamp(
            settings.fee_runner_base + settings.fee_runner_per_km * km,
            settings.fee_runner_min,
            settings.fee_runner_max,
        ),
        2,
    )
    convenience_fee = round(
        max(item_total * settings.fee_convenience_pct, settings.fee_convenience_min), 2
    )
    total = round(item_total + runner_fee + convenience_fee, 2)
    return runner_fee, convenience_fee, total


async def quote(
    db: AsyncSession, campus_id: uuid.UUID, lat: float, lng: float,
    item_total: float, tip: float = 0.0,
) -> dict:
    """Fee breakdown for the checkout UI, without holding anything. `tip` is the
    requester's chosen runner bonus, added on top of the distance-based fee."""
    runner_fee, convenience_fee, _ = await compute_fees(db, campus_id, lat, lng, item_total)
    runner_fee = round(runner_fee + max(tip, 0.0), 2)
    total = round(item_total + runner_fee + convenience_fee, 2)
    return {
        "item_total": round(item_total, 2),
        "runner_fee": runner_fee,
        "convenience_fee": convenience_fee,
        "total": total,
    }


# ----------------------------------------------------------------------- holds

async def place_hold(
    db: AsyncSession,
    campus_id: uuid.UUID,
    requester_id: uuid.UUID,
    errand_id: uuid.UUID,
    lat: float,
    lng: float,
    item_total: float,
    tip: float = 0.0,
) -> EscrowHold:
    """Debit the customer and hold the full amount in escrow. Rides the
    caller's (errand-creation) transaction, so if this raises, no errand is
    persisted either. Raises LedgerError(402) if the wallet is short. `tip`
    (the requester's chosen reward) is folded into the runner fee."""
    await _lock_campus(db, campus_id)  # lock before the balance check closes the race
    runner_fee, convenience_fee, _ = await compute_fees(db, campus_id, lat, lng, item_total)
    runner_fee = round(runner_fee + max(tip, 0.0), 2)
    total = round(item_total + runner_fee + convenience_fee, 2)
    balance = await account_balance(db, campus_id, requester_id)
    if balance < total:
        short = round(total - balance, 2)
        raise LedgerError(
            f"Add ₹{short:.0f} to your wallet to cover this order "
            f"(₹{total:.0f} needed, ₹{balance:.0f} available).",
            402,
        )
    hold = EscrowHold(
        errand_id=errand_id,
        campus_id=campus_id,
        requester_id=requester_id,
        item_total=round(item_total, 2),
        runner_fee=runner_fee,
        convenience_fee=convenience_fee,
        total_amount=total,
        status="HELD",
    )
    db.add(hold)
    await append_entry(db, campus_id, requester_id, "HOLD", -total, errand_id)
    await append_entry(db, campus_id, ESCROW_ACCOUNT, "ESCROW", total, errand_id)
    return hold


async def _actual_item_cost(db: AsyncSession, errand_id: uuid.UUID, budget: float) -> float:
    """What the runner actually spent on items, for reconciliation on release.
    Priced (catalog) orders: sum of AVAILABLE lines — a line the runner marked
    out of stock drops out and its money is refunded. Unpriced (shopping-list /
    gate / parcel) orders have no server-known price, so we settle the budget
    as-is (runner-entered actuals are a later enhancement)."""
    from app.modules.errands.models import ErrandItem

    rows = list(
        await db.scalars(select(ErrandItem).where(ErrandItem.errand_id == errand_id))
    )
    priced = [r for r in rows if r.unit_price_snapshot is not None]
    if not priced:
        return budget
    actual = sum(float(r.unit_price_snapshot) * r.quantity for r in priced if r.is_available)
    return min(round(actual, 2), budget)  # never reimburse more than was held


async def release_hold(db: AsyncSession, errand_id: uuid.UUID) -> dict | None:
    """Split the held funds on completion: reimburse the runner's spend, pay the
    delivery fee, book the convenience charge, refund any unspent budget. Every
    leg is drawn from ESCROW, so the escrow account nets back to zero. Idempotent
    — a redelivered completion event finds the hold already RELEASED and no-ops."""
    hold = await db.scalar(
        select(EscrowHold).where(EscrowHold.errand_id == errand_id).with_for_update()
    )
    if hold is None or hold.status != "HELD":
        return None

    from app.modules.errands.models import Errand

    errand = await db.get(Errand, errand_id)
    runner_id = errand.runner_id if errand else hold.runner_id
    if runner_id is None:
        return None

    item_total = float(hold.item_total)
    reimbursement = await _actual_item_cost(db, errand_id, item_total)
    reward = float(hold.runner_fee)
    convenience = float(hold.convenience_fee)
    refund = round(item_total - reimbursement, 2)

    if reimbursement > 0:
        await append_entry(db, hold.campus_id, runner_id, "REIMBURSEMENT", reimbursement, errand_id)
        await append_entry(db, hold.campus_id, ESCROW_ACCOUNT, "ESCROW", -reimbursement, errand_id)
    if reward > 0:
        await append_entry(db, hold.campus_id, runner_id, "REWARD", reward, errand_id)
        await append_entry(db, hold.campus_id, ESCROW_ACCOUNT, "ESCROW", -reward, errand_id)
    if convenience > 0:
        await append_entry(
            db, hold.campus_id, PLATFORM_ACCOUNT, "CONVENIENCE_FEE", convenience, errand_id
        )
        await append_entry(db, hold.campus_id, ESCROW_ACCOUNT, "ESCROW", -convenience, errand_id)
    if refund > 0:
        await append_entry(db, hold.campus_id, hold.requester_id, "REFUND", refund, errand_id)
        await append_entry(db, hold.campus_id, ESCROW_ACCOUNT, "ESCROW", -refund, errand_id)

    hold.runner_id = runner_id
    hold.status = "RELEASED"
    hold.released_at = datetime.now(UTC)
    hold.version += 1
    return {
        "reward": reward,
        "reimbursement": reimbursement,
        "convenience": convenience,
        "refund": refund,
    }


async def refund_hold(db: AsyncSession, errand_id: uuid.UUID) -> float | None:
    """Return the full held amount to the customer (cancel / expire). Rides the
    caller's transaction. Idempotent by status guard."""
    hold = await db.scalar(
        select(EscrowHold).where(EscrowHold.errand_id == errand_id).with_for_update()
    )
    if hold is None or hold.status != "HELD":
        return None
    total = float(hold.total_amount)
    if total > 0:
        await append_entry(db, hold.campus_id, hold.requester_id, "REFUND", total, errand_id)
        await append_entry(db, hold.campus_id, ESCROW_ACCOUNT, "ESCROW", -total, errand_id)
    hold.status = "REFUNDED"
    hold.refunded_at = datetime.now(UTC)
    hold.version += 1
    return total


# --------------------------------------------------------------------- wallet

async def credit_topup(
    db: AsyncSession, campus_id: uuid.UUID, user_id: uuid.UUID, amount: float
) -> None:
    """Book a wallet top-up as a balanced pair: the user is credited and the
    EXTERNAL float account is debited (money entering from outside). Rides the
    caller's transaction — no commit here."""
    amount = round(amount, 2)
    await _lock_campus(db, campus_id)
    await append_entry(db, campus_id, user_id, "TOPUP", amount)
    await append_entry(db, campus_id, EXTERNAL_ACCOUNT, "TOPUP", -amount)


async def topup(db: AsyncSession, campus_id: uuid.UUID, user_id: uuid.UUID, amount: float) -> float:
    """Fund a wallet via the payment provider (simulated now). Commits its own
    transaction. Returns the new balance."""
    from app.modules.ledger.provider import get_provider

    if amount <= 0:
        raise LedgerError("Enter an amount greater than zero.", 400)
    result = await get_provider().create_topup(str(user_id), amount)
    if not result.ok:
        raise LedgerError("Payment could not be processed. Try again.", 402)
    await credit_topup(db, campus_id, user_id, amount)
    await db.commit()
    return await account_balance(db, campus_id, user_id)


async def wallet_summary(db: AsyncSession, campus_id: uuid.UUID, user_id: uuid.UUID) -> dict:
    balance = await account_balance(db, campus_id, user_id)
    rows = list(
        await db.scalars(
            select(LedgerEntry)
            .where(LedgerEntry.campus_id == campus_id, LedgerEntry.account_id == user_id)
            .order_by(LedgerEntry.seq.desc())
            .limit(50)
        )
    )
    return {"balance": balance, "entries": rows}


# ---------------------------------------------------------------- attach/verify

async def attach_holds(db: AsyncSession, errands: list) -> None:
    """Populate .escrow on each errand for serialization (ErrandOut)."""
    ids = [e.id for e in errands]
    for e in errands:
        e.escrow = None
    if not ids:
        return
    rows = await db.scalars(select(EscrowHold).where(EscrowHold.errand_id.in_(ids)))
    by_id = {h.errand_id: h for h in rows}
    for e in errands:
        h = by_id.get(e.id)
        if h is not None:
            e.escrow = {
                "item_total": float(h.item_total),
                "runner_fee": float(h.runner_fee),
                "convenience_fee": float(h.convenience_fee),
                "total": float(h.total_amount),
                "status": h.status,
            }


async def verify_chain(db: AsyncSession, campus_id: uuid.UUID) -> dict:
    """Walk a campus chain and recompute every HMAC. Returns the first broken
    `seq` (an edited/deleted/inserted row) or reports the chain intact. This is
    the tamper-evidence demo: mutate a row in psql, then call this."""
    entries = list(
        await db.scalars(
            select(LedgerEntry)
            .where(LedgerEntry.campus_id == campus_id)
            .order_by(LedgerEntry.seq.asc())
        )
    )
    prev_hash = GENESIS_HASH
    expected_seq = 1
    for e in entries:
        if e.seq != expected_seq:
            return {"campus_id": str(campus_id), "intact": False, "entries": len(entries),
                    "broken_seq": e.seq, "reason": "sequence gap or reordering"}
        if bytes(e.prev_hash) != prev_hash:
            return {"campus_id": str(campus_id), "intact": False, "entries": len(entries),
                    "broken_seq": e.seq, "reason": "prev_hash mismatch"}
        recomputed = ledger_hmac(
            _canonical(e.seq, e.campus_id, e.account_id, e.errand_id, e.entry_type,
                       float(e.amount), bytes(e.prev_hash), e.created_at)
        )
        if recomputed != bytes(e.entry_hash):
            return {"campus_id": str(campus_id), "intact": False, "entries": len(entries),
                    "broken_seq": e.seq, "reason": "entry_hash mismatch (row was altered)"}
        prev_hash = bytes(e.entry_hash)
        expected_seq += 1
    return {"campus_id": str(campus_id), "intact": True, "entries": len(entries),
            "broken_seq": None, "reason": None}
