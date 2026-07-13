import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import CITEXT, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.mixins import TimestampMixin

ACCOUNT_STATUSES = ("PENDING", "ACTIVE", "SUSPENDED", "BANNED")
ROLES = ("STUDENT", "VENDOR", "ADMIN")


class User(Base, TimestampMixin):
    """A platform account. STUDENT is the default (requester/runner);
    VENDOR operates a campus store (admin-onboarded, no student_id);
    ADMIN runs the place. student_id is required iff role = STUDENT."""

    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("campus_id", "student_id", name="uq_users_campus_student"),
        UniqueConstraint("campus_id", "email", name="uq_users_campus_email"),
        CheckConstraint(
            "account_status IN ('PENDING','ACTIVE','SUSPENDED','BANNED')",
            name="ck_users_account_status",
        ),
        CheckConstraint(
            "reputation_score >= 0 AND reputation_score <= 5", name="ck_users_reputation"
        ),
        CheckConstraint("role IN ('STUDENT','VENDOR','ADMIN')", name="ck_users_role"),
        CheckConstraint(
            "role <> 'STUDENT' OR student_id IS NOT NULL", name="ck_users_student_id_required"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    campus_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("campuses.id"), nullable=False
    )
    student_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    email: Mapped[str] = mapped_column(CITEXT, nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False, server_default="STUDENT")
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    account_status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="PENDING"
    )
    reputation_score: Mapped[float] = mapped_column(
        Numeric(4, 2), nullable=False, server_default="5.00"
    )
    rating_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    credentials: Mapped["AuthCredential"] = relationship(
        back_populates="user", uselist=False, cascade="all, delete-orphan"
    )


class AuthCredential(Base):
    """Password credentials, kept separate from the user profile."""

    __tablename__ = "auth_credentials"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    failed_attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )

    user: Mapped["User"] = relationship(back_populates="credentials")


class RefreshToken(Base):
    """Server-side record of issued refresh tokens (hashed) for revocation."""

    __tablename__ = "refresh_tokens"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    jti: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )
