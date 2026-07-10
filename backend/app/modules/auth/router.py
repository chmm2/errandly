import jwt
from fastapi import APIRouter, Depends, HTTPException, status
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.redis import get_redis
from app.core.security import decode_token
from app.modules.auth import service
from app.modules.auth.dependencies import get_current_user
from app.modules.auth.models import User
from app.modules.auth.schemas import (
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    TokenPair,
    UserOut,
)
from app.modules.campus.models import Campus

router = APIRouter(prefix="/auth", tags=["auth"])


async def _default_campus_id(db: AsyncSession):
    campus = await db.scalar(select(Campus).limit(1))
    if campus is None:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "No campus configured. Run the seed script first.",
        )
    return campus.id


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def register(data: RegisterRequest, db: AsyncSession = Depends(get_db)):
    campus_id = await _default_campus_id(db)
    try:
        return await service.register_user(db, campus_id, data)
    except service.AuthError as e:
        raise HTTPException(e.status_code, e.message) from e


@router.post("/login", response_model=TokenPair)
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
