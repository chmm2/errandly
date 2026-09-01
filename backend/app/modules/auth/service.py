import secrets
import uuid
from datetime import UTC, datetime, timedelta

from redis.asyncio import Redis
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.email import send_email
from app.core.emails.otp import otp_email, otp_subject
from app.core.security import (
    create_access_token,
    create_refresh_token,
    hash_password,
    verify_password,
)
from app.modules.auth.models import (
    AuthCredential,
    EmailOtp,
    PasswordResetOtp,
    RefreshToken,
    User,
)
from app.modules.auth.schemas import RegisterRequest, TokenPair

BLACKLIST_PREFIX = "jwt:blacklist:"
MAX_FAILED_ATTEMPTS = 5
LOCKOUT_MINUTES = 15


def _new_otp() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


async def _issue_email_otp(db: AsyncSession, user: User) -> str | None:
    """Create/replace this user's OTP, email it, and return the code only in
    dev mode (SMTP off) so the caller can surface it for testing. In
    production the code goes out by email and this returns None."""
    code = _new_otp()
    otp = await db.get(EmailOtp, user.id)
    expires = datetime.now(UTC) + timedelta(minutes=settings.otp_ttl_minutes)
    if otp is None:
        db.add(EmailOtp(user_id=user.id, code_hash=hash_password(code), expires_at=expires))
    else:
        otp.code_hash = hash_password(code)
        otp.expires_at = expires
        otp.attempts = 0
    await db.commit()

    text, html = otp_email(user.display_name, code, settings.otp_ttl_minutes)
    sent = await send_email(user.email, otp_subject("verify"), text, html=html)
    return None if sent else code  # dev mode surfaces the code to the caller


class AuthError(Exception):
    """Raised for any authentication/registration failure. Carries an HTTP status."""

    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


async def register_user(
    db: AsyncSession, campus_id: uuid.UUID, data: RegisterRequest
) -> tuple[User, str | None]:
    """Register a student and send an email OTP. Returns (user, dev_otp) —
    dev_otp is set only when SMTP is off, so the flow is testable without a
    mailbox. Verifying the OTP is what activates the account."""
    domain = settings.student_email_domain.strip().lower()
    if domain and not data.email.lower().endswith("@" + domain):
        raise AuthError(f"Registration is restricted to @{domain} email addresses.", 422)

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
        account_status="PENDING",  # activated once the email OTP is verified
    )
    user.credentials = AuthCredential(password_hash=hash_password(data.password))
    db.add(user)
    await db.commit()
    await db.refresh(user)
    dev_otp = await _issue_email_otp(db, user)
    return user, dev_otp


async def verify_email(db: AsyncSession, email: str, code: str) -> User:
    """Check the OTP; on success mark the email verified and activate the
    account (owning a @<campus> inbox is the student proof)."""
    user = await db.scalar(select(User).where(User.email == email, User.deleted_at.is_(None)))
    if user is None:
        raise AuthError("No account found for that email.", 404)
    if user.email_verified_at is not None:
        return user  # already verified — idempotent

    otp = await db.get(EmailOtp, user.id)
    if otp is None:
        raise AuthError("No verification code pending. Request a new one.", 400)
    if otp.expires_at < datetime.now(UTC):
        raise AuthError("That code has expired. Request a new one.", 400)
    if otp.attempts >= settings.otp_max_attempts:
        raise AuthError("Too many attempts. Request a new code.", 429)

    if not verify_password(code, otp.code_hash):
        otp.attempts += 1
        await db.commit()
        raise AuthError("Incorrect code.", 400)

    user.email_verified_at = datetime.now(UTC)
    if user.account_status == "PENDING":
        user.account_status = "ACTIVE"
    await db.delete(otp)
    await db.commit()
    await db.refresh(user)
    return user


async def resend_otp(db: AsyncSession, email: str) -> str | None:
    user = await db.scalar(select(User).where(User.email == email, User.deleted_at.is_(None)))
    if user is None:
        raise AuthError("No account found for that email.", 404)
    if user.email_verified_at is not None:
        raise AuthError("This email is already verified — just log in.", 409)
    return await _issue_email_otp(db, user)


async def request_password_reset(db: AsyncSession, email: str) -> str | None:
    """Email a password-reset code, if that address has an account.

    Never signals whether the account exists — the router returns 202 either
    way. A "no account found" here would turn this endpoint into a free
    membership oracle: anyone could test addresses against it and learn which
    students are registered.
    """
    user = await db.scalar(select(User).where(User.email == email, User.deleted_at.is_(None)))
    if user is None:
        return None
    if user.account_status == "BANNED":
        return None  # nothing to reset into

    code = _new_otp()
    expires = datetime.now(UTC) + timedelta(minutes=settings.otp_ttl_minutes)
    row = await db.get(PasswordResetOtp, user.id)
    if row is None:
        db.add(
            PasswordResetOtp(
                user_id=user.id, code_hash=hash_password(code), expires_at=expires
            )
        )
    else:
        row.code_hash = hash_password(code)
        row.expires_at = expires
        row.attempts = 0
    await db.commit()

    text, html = otp_email(user.display_name, code, settings.otp_ttl_minutes, "reset")
    sent = await send_email(user.email, otp_subject("reset"), text, html=html)
    return None if sent else code


async def reset_password(db: AsyncSession, email: str, code: str, new_password: str) -> None:
    """Verify the reset code and set a new password.

    On success every existing session is revoked. Password reset is the lever
    someone pulls when they think their account is compromised, so leaving the
    attacker's refresh tokens alive would defeat the point of the reset.
    """
    user = await db.scalar(select(User).where(User.email == email, User.deleted_at.is_(None)))
    if user is None:
        raise AuthError("That code didn't work.", 400)

    row = await db.get(PasswordResetOtp, user.id)
    if row is None:
        raise AuthError("No reset code pending. Request a new one.", 400)
    if row.expires_at < datetime.now(UTC):
        raise AuthError("That code has expired. Request a new one.", 400)
    if row.attempts >= settings.otp_max_attempts:
        raise AuthError("Too many attempts. Request a new code.", 429)

    if not verify_password(code, row.code_hash):
        row.attempts += 1
        await db.commit()
        raise AuthError("Incorrect code.", 400)

    cred = await db.get(AuthCredential, user.id)
    cred.password_hash = hash_password(new_password)
    cred.failed_attempts = 0
    cred.locked_until = None  # a correct code clears an existing lockout

    # Receiving mail at the address is the same proof signup asks for, so a
    # user who resets before verifying comes out activated rather than stuck.
    if user.email_verified_at is None:
        user.email_verified_at = datetime.now(UTC)
    if user.account_status == "PENDING":
        user.account_status = "ACTIVE"

    now = datetime.now(UTC)
    await db.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=now)
    )

    await db.delete(row)
    await db.commit()


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
        raise AuthError("Verify your email to activate your account.", 403)

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
