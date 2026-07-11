import uuid
from datetime import datetime
from typing import Any

from geoalchemy2 import Geography
from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    Numeric,
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

    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


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
