import uuid

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.redis import get_redis
from app.core.security import decode_token
from app.modules.auth.models import User
from app.modules.auth.service import is_blacklisted

bearer_scheme = HTTPBearer(auto_error=True)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> User:
    token = credentials.credentials
    try:
        payload = decode_token(token)
    except jwt.PyJWTError as e:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token.") from e

    if payload.get("type") != "access":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Wrong token type.")
    if await is_blacklisted(redis, payload.get("jti", "")):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token has been revoked.")

    user = await db.get(User, uuid.UUID(payload["sub"]))
    if user is None or user.deleted_at is not None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User no longer exists.")
    if user.account_status in ("SUSPENDED", "BANNED"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Account is not permitted.")
    return user


async def require_active_user(user: User = Depends(get_current_user)) -> User:
    if user.account_status != "ACTIVE":
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Account pending verification by an administrator."
        )
    return user


def require_role(*roles: str):
    """RBAC guard factory: role gets you through the door; endpoints still
    check OWNERSHIP of the specific record (role alone is never enough)."""

    async def guard(user: User = Depends(require_active_user)) -> User:
        if user.role not in roles:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, f"Requires role: {' or '.join(roles)}."
            )
        return user

    return guard


require_vendor = require_role("VENDOR")
require_admin = require_role("ADMIN")
