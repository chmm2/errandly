import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, SmallInteger, String, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class TimetableSlot(Base):
    """A recurring class slot. Times are minutes-from-midnight in campus
    time, day_of_week 0=Monday.

    Overlap prevention lives in the DATABASE: an EXCLUDE USING gist
    constraint on (user_id =, day_of_week =, int4range(start,end) &&) —
    two overlapping slots for the same user physically cannot both commit,
    no matter how racy the requests (see migration 0004).
    """

    __tablename__ = "timetable_slots"
    __table_args__ = (
        CheckConstraint("day_of_week BETWEEN 0 AND 6", name="ck_timetable_day"),
        CheckConstraint(
            "start_minute >= 0 AND end_minute <= 1440 AND end_minute > start_minute",
            name="ck_timetable_range",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    day_of_week: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    start_minute: Mapped[int] = mapped_column(Integer, nullable=False)
    end_minute: Mapped[int] = mapped_column(Integer, nullable=False)
    label: Mapped[str] = mapped_column(String(120), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )
