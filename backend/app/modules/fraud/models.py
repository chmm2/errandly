import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.mixins import TimestampMixin

# Where a reference price's current value came from.
#   ADMIN - a human typed or approved it. Authoritative.
#   AUTO  - the trimmed-median estimator moved it, INSIDE the admin band.
PRICE_SOURCES = ("ADMIN", "AUTO")

# ELEVATED: above the reference but under the rupee line — paid in full, but
# counted, because a habit of sitting just under the line is its own signal.
CLAIM_VERDICTS = ("OK", "ELEVATED", "FLAGGED", "NO_REFERENCE")
FLAG_STATUSES = ("OPEN", "UPHELD", "DISMISSED")
PROPOSAL_STATUSES = ("PENDING", "APPROVED", "REJECTED")

# Escalation ladder for repeat offenders. Index = strike number - 1.
STRIKE_ACTIONS = ("WARNING", "REPUTATION_PENALTY", "RUNNER_SUSPENDED", "ACCOUNT_SUSPENDED")


class ReferencePrice(Base, TimestampMixin):
    """What a non-MRP item *should* cost on this campus.

    MRP items carry a printed ceiling and need no reference. Canteen items -
    chicken puffs, tea, samosas - do not, which is exactly where an inflated
    reimbursement claim is unfalsifiable. This table is that missing truth.

    band_min/band_max are the admin's hard bounds. The auto-estimator may move
    reference_price only INSIDE them; drifting to an edge raises a proposal for
    a human instead of silently widening. That bound is what stops the detector
    being trained by the very claims it polices.
    """

    __tablename__ = "reference_prices"
    __table_args__ = (
        UniqueConstraint("campus_id", "item_key", name="uq_reference_campus_item"),
        CheckConstraint("band_min > 0", name="ck_reference_band_min"),
        CheckConstraint("band_max >= band_min", name="ck_reference_band_order"),
        CheckConstraint(
            "reference_price BETWEEN band_min AND band_max", name="ck_reference_in_band"
        ),
        CheckConstraint("source IN ('ADMIN','AUTO')", name="ck_reference_source"),
        CheckConstraint("tolerance_abs > 0", name="ck_reference_tolerance"),
        Index("ix_reference_campus", "campus_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    campus_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("campuses.id"), nullable=False
    )
    # Normalized join key - "Chicken Puffs", "chkn puf" and "chicken  puff"
    # all collapse to "chicken puff" so their claims group together.
    item_key: Mapped[str] = mapped_column(String(120), nullable=False)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)

    reference_price: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    band_min: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    band_max: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    # How many rupees above the reference a single claim may sit before it is
    # flagged outright. Absolute, not a percentage: a flat rupee line is the
    # one a runner at a counter can actually hold in their head, and it is the
    # one an admin can defend to a student without doing arithmetic.
    tolerance_abs: Mapped[float] = mapped_column(
        Numeric(10, 2), nullable=False, server_default="20.00"
    )
    source: Mapped[str] = mapped_column(String(8), nullable=False, server_default="ADMIN")
    sample_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    last_estimated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )


class ReferencePriceProposal(Base):
    """A suggested reference change awaiting an admin's click.

    Raised when the honest-claim median presses against a band edge - i.e.
    puffs genuinely went 20 -> 25 and the band is now wrong. Admins approve or
    reject; they never have to go hunting for stale prices themselves.
    """

    __tablename__ = "reference_price_proposals"
    __table_args__ = (
        CheckConstraint("status IN ('PENDING','APPROVED','REJECTED')", name="ck_proposal_status"),
        CheckConstraint("proposed_price > 0", name="ck_proposal_price"),
        Index("ix_proposal_status", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    reference_price_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("reference_prices.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    proposed_price: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    proposed_band_min: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    proposed_band_max: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    # The evidence, so an admin can judge without opening a query console.
    observed_median: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    sample_count: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="PENDING")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decided_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )


class RunnerPriceClaim(Base):
    """What a runner says they paid for one line at pickup.

    This is the assertion the whole fraud system exists to check. It is stored
    append-only with the reference SNAPSHOT taken at judgement time - so a
    later reference change never silently rewrites whether a past claim was
    fraudulent (same snapshot-vs-reference discipline as errand_items).
    """

    __tablename__ = "runner_price_claims"
    __table_args__ = (
        CheckConstraint("claimed_unit_price >= 0", name="ck_claim_price"),
        CheckConstraint("quantity >= 1", name="ck_claim_quantity"),
        CheckConstraint(
            "verdict IN ('OK','ELEVATED','FLAGGED','NO_REFERENCE')", name="ck_claim_verdict"
        ),
        # One claim per line per errand - resubmitting updates, never stacks.
        UniqueConstraint("errand_id", "item_key", name="uq_claim_errand_item"),
        Index("ix_claim_runner_created", "runner_id", "created_at"),
        Index("ix_claim_item", "campus_id", "item_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    errand_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("errands.id", ondelete="CASCADE"), nullable=False
    )
    runner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    campus_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("campuses.id"), nullable=False
    )
    raw_name: Mapped[str] = mapped_column(String(120), nullable=False)
    item_key: Mapped[str] = mapped_column(String(120), nullable=False)
    claimed_unit_price: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")

    # Snapshot of the judgement, frozen at claim time.
    reference_snapshot: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    # The rupee line this claim was judged against, frozen at judgement time.
    threshold_snapshot: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    delta_pct: Mapped[float | None] = mapped_column(Numeric(7, 2), nullable=True)
    # Rupees over the reference. Stored rather than derived so the
    # "walking the line" query needs no join and no live reference lookup.
    delta_abs: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    verdict: Mapped[str] = mapped_column(String(16), nullable=False, server_default="OK")
    # Amount actually eligible for reimbursement - capped at reference when
    # flagged. The payout path reads THIS, never claimed_unit_price.
    eligible_amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )


class FraudFlag(Base):
    """One suspicious observation about one user.

    A single flag is not guilt - a runner may genuinely have paid more once.
    Punishment keys off the PATTERN (see count_upheld_flags), which is what
    "constantly quoting higher" actually means.
    """

    __tablename__ = "fraud_flags"
    __table_args__ = (
        CheckConstraint("status IN ('OPEN','UPHELD','DISMISSED')", name="ck_flag_status"),
        CheckConstraint("severity BETWEEN 1 AND 3", name="ck_flag_severity"),
        Index("ix_flag_user_created", "user_id", "created_at"),
        Index("ix_flag_status", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    errand_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("errands.id", ondelete="SET NULL"), nullable=True
    )
    claim_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("runner_price_claims.id", ondelete="SET NULL"),
        nullable=True,
    )
    rule: Mapped[str] = mapped_column(String(48), nullable=False)
    severity: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    details: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="OPEN")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )


class UserStrike(Base):
    """An applied punishment, append-only.

    Strikes are never deleted - lifting one writes lifted_at, so the history of
    what was done to an account survives an admin changing their mind.
    """

    __tablename__ = "user_strikes"
    __table_args__ = (
        CheckConstraint("level >= 1", name="ck_strike_level"),
        CheckConstraint(
            "action IN ('WARNING','REPUTATION_PENALTY','RUNNER_SUSPENDED','ACCOUNT_SUSPENDED')",
            name="ck_strike_action",
        ),
        Index("ix_strike_user_created", "user_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    flag_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("fraud_flags.id", ondelete="SET NULL"), nullable=True
    )
    level: Mapped[int] = mapped_column(Integer, nullable=False)
    action: Mapped[str] = mapped_column(String(24), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    lifted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )
