import uuid

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    Integer,
    Numeric,
    String,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.mixins import TimestampMixin

VENDOR_CATEGORIES = ("FOOD", "GROCERY", "STATIONERY", "PHARMACY")


class Vendor(Base, TimestampMixin):
    """An in-campus store/canteen, operated by its owner account
    (role=VENDOR). Vendors maintain their own menus — the platform never
    edits them on their behalf."""

    __tablename__ = "vendors"
    __table_args__ = (
        CheckConstraint(
            "category IN ('FOOD','GROCERY','STATIONERY','PHARMACY')",
            name="ck_vendors_category",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    campus_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("campuses.id"), nullable=False
    )
    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, unique=True
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    category: Mapped[str] = mapped_column(String(16), nullable=False)
    description: Mapped[str | None] = mapped_column(String(300), nullable=True)
    is_open: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))


class MenuItem(Base, TimestampMixin):
    """One orderable item on a vendor's menu, grouped by section."""

    __tablename__ = "menu_items"
    __table_args__ = (CheckConstraint("price >= 0", name="ck_menu_items_price"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    vendor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("vendors.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    section: Mapped[str] = mapped_column(String(80), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    price: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    is_available: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    position: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
