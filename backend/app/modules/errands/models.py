import uuid
from datetime import datetime
from typing import Any

from geoalchemy2 import Geography
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    Numeric,
    SmallInteger,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.mixins import TimestampMixin

CATEGORIES = ("FOOD", "GROCERY", "PARCEL", "STATIONERY", "PHARMACY", "CUSTOM")
STATUSES = ("OPEN", "ACCEPTED", "IN_PROGRESS", "DELIVERED", "COMPLETED", "CANCELLED", "EXPIRED")

# How the errand is fulfilled — derived from category at creation.
# CATALOG: buy/collect from an in-campus vendor. GATE_PICKUP: collect an
# external order at the Main Gate. PARCEL_POINT: campus parcel collection point.
FULFILLMENT_TYPES = ("CATALOG", "GATE_PICKUP", "PARCEL_POINT")
CATEGORY_FULFILLMENT = {
    "FOOD": "CATALOG",
    "GROCERY": "CATALOG",
    "STATIONERY": "CATALOG",
    "PHARMACY": "CATALOG",
    "CUSTOM": "GATE_PICKUP",
    "PARCEL": "PARCEL_POINT",
}


class Errand(Base, TimestampMixin):
    """A requested errand. Lifecycle is a guarded state machine; every change
    is mirrored into errand_events (append-only audit)."""

    __tablename__ = "errands"
    __table_args__ = (
        CheckConstraint(
            "category IN ('FOOD','GROCERY','PARCEL','STATIONERY','PHARMACY','CUSTOM')",
            name="ck_errands_category",
        ),
        CheckConstraint(
            "status IN ('OPEN','ACCEPTED','IN_PROGRESS','DELIVERED','COMPLETED',"
            "'CANCELLED','EXPIRED')",
            name="ck_errands_status",
        ),
        CheckConstraint("reward >= 0", name="ck_errands_reward"),
        CheckConstraint(
            "fulfillment_type IN ('CATALOG','GATE_PICKUP','PARCEL_POINT')",
            name="ck_errands_fulfillment_type",
        ),
        CheckConstraint("collect_amount >= 0", name="ck_errands_collect_amount"),
        Index("ix_errands_campus_status", "campus_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    campus_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("campuses.id"), nullable=False
    )
    requester_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    runner_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True, index=True
    )

    category: Mapped[str] = mapped_column(String(16), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    pickup_label: Mapped[str] = mapped_column(String(200), nullable=False)

    # drop_point (geography) powers spatial queries; lat/lng mirror it for cheap
    # serialization — both are set together in the service, never independently.
    drop_point = mapped_column(
        Geography(geometry_type="POINT", srid=4326, spatial_index=False), nullable=False
    )
    drop_lat: Mapped[float] = mapped_column(Numeric(9, 6), nullable=False)
    drop_lng: Mapped[float] = mapped_column(Numeric(9, 6), nullable=False)
    drop_label: Mapped[str | None] = mapped_column(String(200), nullable=True)

    # Catalog orders: which store the runner buys from.
    vendor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("vendors.id"), nullable=True
    )
    reward: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    fulfillment_type: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="CATALOG"
    )
    # External order/tracking number for gate & parcel pickups — shown only
    # to the requester and the assigned runner, never in the public feed.
    external_ref: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # Cash the runner pays/hands over at pickup; reimbursed via the ledger
    # (Sprint 5) on top of the reward.
    collect_amount: Mapped[float] = mapped_column(
        Numeric(12, 2), nullable=False, server_default="0"
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="OPEN")
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")

    # Poster-chosen deadline: OPEN errands past this are swept to EXPIRED.
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ErrandItem(Base):
    """One order line of a catalog errand. Name and unit price are SNAPSHOTS
    taken at order time — menu edits and deletions never rewrite history
    (snapshot vs reference; menu_item_id is a weak link kept for analytics)."""

    __tablename__ = "errand_items"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    errand_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("errands.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    menu_item_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("menu_items.id", ondelete="SET NULL"), nullable=True
    )
    name_snapshot: Mapped[str] = mapped_column(String(120), nullable=False)
    # Priceless for shopping-list lines (grocery/stationery/pharmacy).
    unit_price_snapshot: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    # Runner flips this false when a store is out of an item.
    is_available: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    # Per-item detail the requester added (brand, size, flavour…).
    note: Mapped[str | None] = mapped_column(String(200), nullable=True)


class ErrandHandoffSecret(Base):
    """Delivery OTP for gate/parcel pickups, encrypted at rest.

    Never serialized with the errand. Disclosed only to the assigned runner
    after accept, via a dedicated endpoint that writes a SECRET_VIEWED event.
    """

    __tablename__ = "errand_handoff_secrets"

    errand_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("errands.id", ondelete="CASCADE"),
        primary_key=True,
    )
    otp_ciphertext: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )


class Rating(Base):
    """One rating per completed errand (PK = errand_id enforces it).
    Feeds users.reputation_score, which matching reads."""

    __tablename__ = "ratings"
    __table_args__ = (CheckConstraint("stars BETWEEN 1 AND 5", name="ck_ratings_stars"),)

    errand_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("errands.id", ondelete="CASCADE"), primary_key=True
    )
    rater_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    ratee_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    stars: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    comment: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )


class ErrandEvent(Base):
    """Append-only audit trail: one row per lifecycle transition (event sourcing)."""

    __tablename__ = "errand_events"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    errand_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("errands.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )


class OfferLog(Base):
    """Why each runner was offered an errand — the counterfactual record.

    Matching ranks candidates by effective distance:

        effective = distance
                  - trust      x SOCIAL_WEIGHT_M
                  - (rep - 3.5) x REPUTATION_WEIGHT_M
                  + open-flag penalty

    Those terms are computed, used to order the offer, and then thrown away.
    That loss is the reason a whole class of question cannot be asked.

    Errandly boosts friends up the queue AND treats friends transacting with
    each other as evidence of a collusion ring. The first causes the second, so
    `circulation` partly measures the router rather than the people. Separating
    them needs the one thing nothing currently stores: what the policy EXPECTED
    to happen, against which what actually happened can be compared. Only the
    part the policy cannot explain is evidence about anybody.

    Written once per offer round — an errand that is escalated, widened or
    handed back produces several rows, which is correct: each round was a
    separate decision taken under different information.

    Analytics only. Nothing reads this on a request path, and a failure to
    write it must never stop an errand being offered.
    """

    __tablename__ = "offer_logs"
    __table_args__ = (
        Index("ix_offer_log_errand", "errand_id"),
        Index("ix_offer_log_requester", "requester_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    errand_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("errands.id", ondelete="CASCADE"), nullable=False
    )
    requester_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    campus_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("campuses.id"), nullable=False
    )

    # Which dispatch round this was for the errand: 1 on first offer, 2 after a
    # hand-back or an escalation, and so on.
    round_no: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")

    # The hop ceiling in force for this round, or null when unrestricted. A
    # narrower ceiling is itself part of why a candidate was or was not offered.
    max_hops: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)

    # One entry per candidate, in the order they were offered:
    #   {runner_id, distance_m, trust, hops, reputation, penalty, effective, rank}
    # `effective` is the score that decided the order; the rest are the terms it
    # was built from, kept so the counterfactual ("rank with trust zeroed") can
    # be recomputed without re-deriving anything from a graph that has since
    # moved on.
    candidates: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)

    # Filled in if somebody took it. Null means this round found no taker,
    # which is data, not a gap.
    accepted_runner_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    accepted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )
