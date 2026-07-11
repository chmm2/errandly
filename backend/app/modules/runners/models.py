import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.mixins import TimestampMixin


class RunnerProfile(Base, TimestampMixin):
    """Runner-mode state for a user.

    Postgres is the truth for availability; the Redis GEO index
    (runners:geo:{campus_id}) is a derived, eventually-consistent copy used
    for fast nearby lookups — rebuild it from here if Redis loses it.
    """

    __tablename__ = "runner_profiles"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    campus_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("campuses.id"), nullable=False
    )
    is_available: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    max_load: Mapped[int] = mapped_column(Integer, nullable=False, server_default="2")
    last_lat: Mapped[float | None] = mapped_column(Numeric(9, 6), nullable=True)
    last_lng: Mapped[float | None] = mapped_column(Numeric(9, 6), nullable=True)
    location_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
