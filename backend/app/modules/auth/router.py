import jwt
from fastapi import APIRouter, Depends, HTTPException, Response, status
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.ratelimit import RateLimiter
from app.core.redis import get_redis
from app.core.security import decode_token
from app.modules.auth import service
from app.modules.auth.dependencies import get_current_user
from app.modules.auth.models import User
from app.modules.auth.schemas import (
    ForgotPasswordRequest,
    LoginRequest,
    PhotoUpdate,
    RefreshRequest,
    RegisterRequest,
    ResendOtpRequest,
    ResetPasswordRequest,
    TokenPair,
    UserOut,
    VerifyEmailRequest,
)
from app.modules.campus.models import Campus

router = APIRouter(prefix="/auth", tags=["auth"])

login_limiter = RateLimiter(times=10, seconds=60, scope="login")
otp_limiter = RateLimiter(times=5, seconds=60, scope="otp")
# Tighter than the OTP issue limit: this endpoint is the one an attacker would
# use to brute-force a 6-digit code, and per-user attempt counting alone can be
# sidestepped by cycling target addresses.
reset_limiter = RateLimiter(times=10, seconds=60, scope="reset")


def _dev_otp_header(response: Response, dev_otp: str | None) -> None:
    """In dev mode (SMTP off) the code isn't emailed, so hand it back via a
    header the frontend can read to keep the flow testable. No-op in prod."""
    if dev_otp is not None:
        response.headers["X-Dev-OTP"] = dev_otp


async def _default_campus_id(db: AsyncSession):
    campus = await db.scalar(select(Campus).limit(1))
    if campus is None:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "No campus configured. Run the seed script first.",
        )
    return campus.id


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def register(data: RegisterRequest, response: Response, db: AsyncSession = Depends(get_db)):
    campus_id = await _default_campus_id(db)
    try:
        user, dev_otp = await service.register_user(db, campus_id, data)
    except service.AuthError as e:
        raise HTTPException(e.status_code, e.message) from e
    _dev_otp_header(response, dev_otp)
    return user


@router.post("/verify-email", response_model=TokenPair)
async def verify_email(
    data: VerifyEmailRequest,
    db: AsyncSession = Depends(get_db),
):
    """Confirm the OTP → activates the account and logs the student straight in."""
    try:
        user = await service.verify_email(db, data.email, data.code)
        return await service._issue_tokens(db, user)
    except service.AuthError as e:
        raise HTTPException(e.status_code, e.message) from e


@router.post("/resend-otp", status_code=status.HTTP_202_ACCEPTED,
             dependencies=[Depends(otp_limiter)])
async def resend_otp(
    data: ResendOtpRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    try:
        dev_otp = await service.resend_otp(db, data.email)
    except service.AuthError as e:
        raise HTTPException(e.status_code, e.message) from e
    _dev_otp_header(response, dev_otp)
    return {"status": "sent"}


@router.post(
    "/forgot-password",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(otp_limiter)],
)
async def forgot_password(
    data: ForgotPasswordRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    """Start a password reset. Always 202, whether or not the account exists —
    see service.request_password_reset for why."""
    dev_otp = await service.request_password_reset(db, data.email)
    _dev_otp_header(response, dev_otp)
    return {"status": "sent"}


@router.post("/reset-password", dependencies=[Depends(reset_limiter)])
async def reset_password(data: ResetPasswordRequest, db: AsyncSession = Depends(get_db)):
    """Finish a password reset. Revokes every existing session on success, so
    the client must log in again with the new password."""
    try:
        await service.reset_password(db, data.email, data.code, data.new_password)
    except service.AuthError as e:
        raise HTTPException(e.status_code, e.message) from e
    return {"status": "ok"}


@router.post("/login", response_model=TokenPair, dependencies=[Depends(login_limiter)])
async def login(data: LoginRequest, db: AsyncSession = Depends(get_db)):
    try:
        return await service.login(db, data.email, data.password)
    except service.AuthError as e:
        raise HTTPException(e.status_code, e.message) from e


@router.post("/refresh", response_model=TokenPair)
async def refresh(
    data: RefreshRequest,
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
):
    try:
        payload = decode_token(data.refresh_token)
    except jwt.PyJWTError as e:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "Invalid or expired refresh token."
        ) from e
    if payload.get("type") != "refresh":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Wrong token type.")
    try:
        return await service.refresh_tokens(db, redis, payload["sub"], payload["jti"])
    except service.AuthError as e:
        raise HTTPException(e.status_code, e.message) from e


@router.get("/me", response_model=UserOut)
async def me(current_user: User = Depends(get_current_user)):
    return current_user


@router.put("/me/photo", response_model=UserOut)
async def set_photo(
    data: PhotoUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Set (or clear) your profile photo — a small avatar the requester sees
    on the tracking screen while you're running their errand."""
    current_user.photo_url = data.photo_url
    await db.commit()
    await db.refresh(current_user)
    return current_user
