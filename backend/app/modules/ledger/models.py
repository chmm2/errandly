import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Numeric, String, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

ENTRY_TYPES = ("REWARD", "REIMBURSEMENT")


class LedgerEntry(Base):
    """Append-only money. Balances are DERIVED (SUM), never stored and
    mutated — you can't corrupt a balance you never write. Entries are
    created only by the settlement consumer, never by request handlers.
    KARMA units now; a UPI payout would read this same table."""

    __tablename__ = "ledger_entries"
    __table_args__ = (
        CheckConstraint("entry_type IN ('REWARD','REIMBURSEMENT')", name="ck_ledger_type"),
        CheckConstraint("amount > 0", name="ck_ledger_amount"),
        Index("ix_ledger_user_created", "user_id", "created_at"),
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
    amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )
