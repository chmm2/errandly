import uuid

from geoalchemy2 import Geography
from sqlalchemy import String, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.mixins import TimestampMixin


class Campus(Base, TimestampMixin):
    """A university campus. Tenancy anchor — every scoped entity references a campus."""

    __tablename__ = "campuses"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    country: Mapped[str] = mapped_column(String(2), nullable=False, server_default="IN")
    timezone: Mapped[str] = mapped_column(
        String(64), nullable=False, server_default="Asia/Kolkata"
    )
    center: Mapped[object | None] = mapped_column(Geography("POINT", srid=4326), nullable=True)
