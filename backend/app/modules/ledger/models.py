import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    Numeric,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

# System accounts are not real users — they are fixed sentinel ids that the
# double-entry ledger books against. ESCROW holds a customer's money while an
# errand is in flight; PLATFORM collects the convenience charge; EXTERNAL is
# the float-liability counter-leg for wallet top-ups (money entering from the
# outside world), so even a top-up is balanced and the ledger sums to zero.
# Because these are not rows in `users`, ledger_entries.account_id has NO FK.
ESCROW_ACCOUNT = uuid.UUID("00000000-0000-0000-0000-0000000000e5")
PLATFORM_ACCOUNT = uuid.UUID("00000000-0000-0000-0000-0000000000b1")
EXTERNAL_ACCOUNT = uuid.UUID("00000000-0000-0000-0000-0000000000ff")

# Signed money movements. Credits are positive, debits negative, so a party's
# balance is simply SUM(amount). Every business action books a BALANCED PAIR
# (equal-and-opposite legs), which is why the whole ledger always sums to 0 —
# even a top-up, whose counter-leg lands on the EXTERNAL float account.
#   TOPUP           +/-  customer wallet (+) vs EXTERNAL float (-)
#   HOLD            -  customer, when an order is posted
#   ESCROW          ±  the ESCROW account: + as the hold's counter-leg,
#                      - as each payout/refund leg on release
#   REWARD          +  runner, the delivery fee, on completion
#   REIMBURSEMENT   +  runner, the item cost fronted at the shop
#   CONVENIENCE_FEE +  PLATFORM, on completion
#   REFUND          +  customer, unspent budget or a cancelled/expired hold
ENTRY_TYPES = (
    "TOPUP",
    "HOLD",
    "ESCROW",
    "REWARD",
    "REIMBURSEMENT",
    "CONVENIENCE_FEE",
    "REFUND",
)

# Escrow hold lifecycle — a small state machine parallel to the errand's.
HOLD_STATUSES = ("HELD", "RELEASED", "REFUNDED")


class LedgerEntry(Base):
    """Append-only, HMAC-hash-chained money log. Balances are DERIVED (SUM),
    never stored and mutated — you can't corrupt a balance you never write.

    Tamper-evidence: entries form a chain PER CAMPUS (the project's shard key).
    Each row's `entry_hash` is HMAC(key, seq · campus · account · errand ·
    type · amount · prev_hash · created_at). Edit or delete any row and every
    later hash stops matching; `service.verify_chain` walks the chain and names
    the first broken `seq`. Appends are serialized under a per-campus advisory
    lock so the chain stays linear (see service.append_entry)."""

    __tablename__ = "ledger_entries"
    __table_args__ = (
        CheckConstraint(
            "entry_type IN ('TOPUP','HOLD','ESCROW','REWARD',"
            "'REIMBURSEMENT','CONVENIENCE_FEE','REFUND')",
            name="ck_ledger_type",
        ),
        CheckConstraint("amount <> 0", name="ck_ledger_amount"),
        UniqueConstraint("campus_id", "seq", name="uq_ledger_campus_seq"),
        Index("ix_ledger_account_created", "account_id", "created_at"),
        Index("ix_ledger_campus_seq", "campus_id", "seq"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    campus_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("campuses.id"), nullable=False
    )
    # Position of this entry in its campus chain (1, 2, 3, …).
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    # A real user id OR a system-account sentinel (ESCROW/PLATFORM). No FK on
    # purpose: system accounts have no users row.
    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    errand_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("errands.id"), nullable=True
    )
    entry_type: Mapped[str] = mapped_column(String(20), nullable=False)
    amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    # Chain links. Genesis (first entry of a campus) uses 32 zero bytes.
    prev_hash: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    entry_hash: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    # Set explicitly by the app (not a server default) because it is part of
    # the hashed canonical form and must be identical on re-verification.
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class EscrowHold(Base):
    """One row per errand: the money held while it is in flight. The amounts
    are the SNAPSHOT quoted to the customer at post time; the actual split is
    reconciled and booked to the ledger on release. Status is the guarded
    state machine HELD → RELEASED / REFUNDED (mirrors the errand FSM)."""

    __tablename__ = "escrow_holds"
    __table_args__ = (
        CheckConstraint(
            "status IN ('HELD','RELEASED','REFUNDED')", name="ck_escrow_status"
        ),
        CheckConstraint("total_amount >= 0", name="ck_escrow_total"),
    )

    errand_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("errands.id", ondelete="CASCADE"), primary_key=True
    )
    campus_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("campuses.id"), nullable=False
    )
    requester_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    runner_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    # item_total is the priced cart, or the customer's budget for unpriced
    # (shopping-list / gate / parcel) orders.
    item_total: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    runner_fee: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    convenience_fee: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    total_amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="HELD")
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    held_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    refunded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
