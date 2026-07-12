import uuid
from datetime import date

from sqlalchemy import Date, ForeignKey, Integer, Numeric
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class DailyStat(Base):
    """Per-campus per-day counters, upserted by the analytics consumer.
    Deliberately tiny — the pattern (event stream → derived read model)
    is the point, Spark is not needed to count errands on one campus."""

    __tablename__ = "daily_stats"

    campus_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("campuses.id"), primary_key=True
    )
    stat_date: Mapped[date] = mapped_column(Date, primary_key=True)
    orders_created: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    orders_completed: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    orders_cancelled: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    reward_total: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, server_default="0")
