import uuid
from datetime import UTC, datetime, timedelta

from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import (
    create_access_token,
    create_refresh_token,
    hash_password,
    verify_password,
)
from app.modules.auth.models import AuthCredential, RefreshToken, User
from app.modules.auth.schemas import RegisterRequest, TokenPair

BLACKLIST_PREFIX = "jwt:blacklist:"
MAX_FAILED_ATTEMPTS = 5
LOCKOUT_MINUTES = 15


class AuthError(Exception):
    """Raised for any authentication/registration failure. Carries an HTTP status."""

    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


async def register_user(db: AsyncSession, campus_id: uuid.UUID, data: RegisterRequest) -> User:
    existing = await db.scalar(
        select(User).where(
            User.campus_id == campus_id,
            (User.student_id == data.student_id) | (User.email == data.email),
        )
    )
    if existing:
        raise AuthError("A user with this Student ID or email already exists.", 409)

    user = User(
        campus_id=campus_id,
        student_id=data.student_id,
        email=data.email,
        display_name=data.display_name,
        phone=data.phone,
        account_status="PENDING",  # admin approves before ACTIVE
    )
    user.credentials = AuthCredential(password_hash=hash_password(data.password))
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def _issue_tokens(db: AsyncSession, user: User) -> TokenPair:
    access, _ = create_access_token(str(user.id))
    refresh, refresh_jti = create_refresh_token(str(user.id))
    db.add(
        RefreshToken(
            user_id=user.id,
            jti=refresh_jti,
            expires_at=datetime.now(UTC)
            + timedelta(days=settings.refresh_token_expire_days),
        )
    )
    await db.commit()
    return TokenPair(access_token=access, refresh_token=refresh)


async def login(db: AsyncSession, email: str, password: str) -> TokenPair:
    user = await db.scalar(select(User).where(User.email == email, User.deleted_at.is_(None)))
    if user is None:
        raise AuthError("Invalid email or password.", 401)

    cred = await db.get(AuthCredential, user.id)
    now = datetime.now(UTC)
    if cred.locked_until and cred.locked_until > now:
        raise AuthError("Account temporarily locked. Try again later.", 423)

    if not verify_password(password, cred.password_hash):
        cred.failed_attempts += 1
        if cred.failed_attempts >= MAX_FAILED_ATTEMPTS:
            cred.locked_until = now + timedelta(minutes=LOCKOUT_MINUTES)
            cred.failed_attempts = 0
        await db.commit()
        raise AuthError("Invalid email or password.", 401)

    if user.account_status == "BANNED":
        raise AuthError("This account has been banned.", 403)
    if user.account_status == "SUSPENDED":
        raise AuthError("This account is suspended.", 403)
    if user.account_status == "PENDING":
        raise AuthError("Account pending verification by an administrator.", 403)

    cred.failed_attempts = 0
    cred.locked_until = None
    await db.commit()
    return await _issue_tokens(db, user)


async def refresh_tokens(db: AsyncSession, redis: Redis, user_id: str, jti: str) -> TokenPair:
    record = await db.scalar(select(RefreshToken).where(RefreshToken.jti == jti))
    if record is None or record.revoked_at is not None:
        raise AuthError("Refresh token is invalid or has been revoked.", 401)

    record.revoked_at = datetime.now(UTC)  # rotate: single-use refresh tokens
    user = await db.get(User, uuid.UUID(user_id))
    if user is None or user.account_status != "ACTIVE":
        await db.commit()
        raise AuthError("Account is not active.", 403)
    return await _issue_tokens(db, user)


async def is_blacklisted(redis: Redis, jti: str) -> bool:
    return await redis.exists(f"{BLACKLIST_PREFIX}{jti}") == 1
