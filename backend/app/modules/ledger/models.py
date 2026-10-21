import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

# CREDIT adds to a wallet, DEBIT removes from it. Amount is ALWAYS positive —
# direction carries the sign, so the "amount > 0" invariant survives escrow.
DIRECTIONS = ("CREDIT", "DEBIT")

ENTRY_TYPES = (
    "TOPUP",          # CREDIT  requester funds their wallet
    "HOLD",           # DEBIT   requester's money moves into escrow at order time
    "REFUND",         # CREDIT  escrow returned (cancel/expire/over-hold)
    "REWARD",         # CREDIT  runner's fee on completion
    "REIMBURSEMENT",  # CREDIT  runner repaid for cash fronted at pickup
    "REVIEW_PAYOUT",  # CREDIT  withheld money released to a runner after review
    "REVIEW_REFUND",  # CREDIT  withheld money returned to a requester after review
    "CLAWBACK",       # DEBIT   fraud adjustment against a runner
)

# Which direction each type must carry. Enforced in the service, mirrored by a
# CHECK so a bad row can't be written even by hand.
ENTRY_DIRECTION = {
    "TOPUP": "CREDIT",
    "HOLD": "DEBIT",
    "REFUND": "CREDIT",
    "REWARD": "CREDIT",
    "REIMBURSEMENT": "CREDIT",
    "REVIEW_PAYOUT": "CREDIT",
    "REVIEW_REFUND": "CREDIT",
    "CLAWBACK": "DEBIT",
}

HOLD_STATUSES = ("HELD", "RELEASED", "REFUNDED", "PENDING_REVIEW")


class LedgerEntry(Base):
    """Append-only money. Balances are DERIVED (SUM credits - SUM debits),
    never stored and mutated — you can't corrupt a balance you never write.
    Entries are written only by the ledger service, never by request handlers
    reaching in directly. KARMA units now; a UPI payout would read this table."""

    __tablename__ = "ledger_entries"
    __table_args__ = (
        CheckConstraint(
            "entry_type IN ('TOPUP','HOLD','REFUND','REWARD','REIMBURSEMENT',"
            "'REVIEW_PAYOUT','REVIEW_REFUND','CLAWBACK')",
            name="ck_ledger_type",
        ),
        CheckConstraint("direction IN ('CREDIT','DEBIT')", name="ck_ledger_direction"),
        CheckConstraint("amount > 0", name="ck_ledger_amount"),
        # Type and direction can't disagree — HOLD is never a credit.
        CheckConstraint(
            "(entry_type IN ('HOLD','CLAWBACK') AND direction = 'DEBIT') OR "
            "(entry_type IN ('TOPUP','REFUND','REWARD','REIMBURSEMENT',"
            "'REVIEW_PAYOUT','REVIEW_REFUND') AND direction = 'CREDIT')",
            name="ck_ledger_type_direction",
        ),
        Index("ix_ledger_user_created", "user_id", "created_at"),
        Index("ix_ledger_errand", "errand_id"),
        # Idempotency: one entry per (errand, user, type). A Kafka redelivery
        # or a double-clicked button collides here instead of paying twice.
        # This is why post-review money uses its OWN types: a review payout to
        # a runner who was already reimbursed on the same errand is a second,
        # legitimate payment, and reusing REIMBURSEMENT would have made the
        # constraint swallow it silently.
        UniqueConstraint(
            "errand_id", "user_id", "entry_type", name="uq_ledger_errand_user_type"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    errand_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("errands.id"), nullable=True
    )
    entry_type: Mapped[str] = mapped_column(String(16), nullable=False)
    direction: Mapped[str] = mapped_column(String(8), nullable=False, server_default="CREDIT")
    amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    memo: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )


class EscrowHold(Base):
    """The requester's money, parked between order and delivery.

    One hold per errand (PK enforces it). The hold is the ONLY thing the
    runner's payout is drawn from — a payout can never exceed what was held,
    so the platform cannot be made to pay out money it never collected.
    """

    __tablename__ = "escrow_holds"
    __table_args__ = (
        CheckConstraint(
            "status IN ('HELD','RELEASED','REFUNDED','PENDING_REVIEW')",
            name="ck_escrow_status",
        ),
        CheckConstraint("amount > 0", name="ck_escrow_amount"),
        CheckConstraint("released_amount >= 0", name="ck_escrow_released"),
        CheckConstraint("released_amount <= amount", name="ck_escrow_no_overdraw"),
        Index("ix_escrow_status", "status"),
    )

    errand_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("errands.id", ondelete="CASCADE"), primary_key=True
    )
    requester_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    # Breakdown of what was held, kept for the receipt the requester sees.
    items_total: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, server_default="0")
    reward: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, server_default="0")
    collect_amount: Mapped[float] = mapped_column(
        Numeric(12, 2), nullable=False, server_default="0"
    )
    # Headroom held on top of the estimated spend, so a shop charging more than
    # expected does not leave the runner unpaid. Returned to the requester at
    # settlement to whatever extent it was not needed.
    buffer: Mapped[float] = mapped_column(
        Numeric(12, 2), nullable=False, server_default="0"
    )
    # The slice of the estimate the headroom was charged on - the non-MRP
    # goods. Stored rather than derived: buffer / pct only reconstructs it
    # while the percentage is unchanged, and a receipt has to survive a
    # retune.
    buffer_base: Mapped[float] = mapped_column(
        Numeric(12, 2), nullable=False, server_default="0"
    )
    amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    released_amount: Mapped[float] = mapped_column(
        Numeric(12, 2), nullable=False, server_default="0"
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="HELD")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )
    settled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
