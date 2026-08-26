import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Friendship(Base):
    """A friend link between two students, and the source of truth for it.

    Stored once per pair, not twice. `user_lo`/`user_hi` are the two ids in
    sorted order, which makes the unique constraint do real work: without an
    ordering, (A,B) and (B,A) are different rows and a pair could be befriended
    twice, or accepted from both ends into two conflicting states.

    `requested_by` remembers who asked, since the ordering above deliberately
    discards direction. That is what lets the recipient — and only the
    recipient — accept.

    Status is PENDING → ACCEPTED, or PENDING → DECLINED, or either → BLOCKED.
    Rows are kept after decline/block rather than deleted: re-requesting
    someone who declined should not be free, and an unblock needs something to
    unblock.
    """

    __tablename__ = "friendships"
    __table_args__ = (
        UniqueConstraint("user_lo", "user_hi", name="uq_friendship_pair"),
        CheckConstraint("user_lo < user_hi", name="ck_friendship_ordered"),
        CheckConstraint(
            "status IN ('PENDING','ACCEPTED','DECLINED','BLOCKED')",
            name="ck_friendship_status",
        ),
        # The two hot reads: "my friends" and "my pending requests".
        Index("ix_friendship_lo_status", "user_lo", "status"),
        Index("ix_friendship_hi_status", "user_hi", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_lo: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    user_hi: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    requested_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="PENDING")
    # Set when a BLOCK is applied, so an unblock can restore the prior state
    # instead of guessing whether these two were ever friends.
    status_before_block: Mapped[str | None] = mapped_column(String(16), nullable=True)
    blocked_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )
    responded_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


def pair(a: uuid.UUID, b: uuid.UUID) -> tuple[uuid.UUID, uuid.UUID]:
    """The (lo, hi) ordering used by Friendship. See the class docstring."""
    return (a, b) if str(a) < str(b) else (b, a)
