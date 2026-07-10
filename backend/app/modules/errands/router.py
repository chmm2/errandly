import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.ratelimit import RateLimiter
from app.core.redis import get_redis
from app.modules.auth.dependencies import require_active_user
from app.modules.auth.models import User
from app.modules.errands import service
from app.modules.errands.schemas import (
    CancelRequest,
    ErrandCreate,
    ErrandEventOut,
    ErrandFeed,
    ErrandOut,
    HandoffSecretOut,
    MyErrands,
)
from app.modules.errands.service import ErrandError

router = APIRouter(prefix="/errands", tags=["errands"])

create_limiter = RateLimiter(times=10, seconds=60, scope="errand_create")


def _raise(e: ErrandError) -> None:
    raise HTTPException(e.status_code, e.message) from e


@router.post("", response_model=ErrandOut, status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(create_limiter)])
async def create_errand(
    data: ErrandCreate,
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
):
    return await service.create_errand(db, redis, user, data)


@router.get("", response_model=ErrandFeed)
async def feed(
    limit: int = Query(default=20, ge=1, le=50),
    offset: int = Query(default=0, ge=0),
    lat: float | None = Query(default=None, ge=-90, le=90),
    lng: float | None = Query(default=None, ge=-180, le=180),
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_db),
):
    items, total = await service.list_feed(db, user, limit, offset, lat=lat, lng=lng)
    return ErrandFeed(items=items, limit=limit, offset=offset, total=total)


@router.get("/mine", response_model=MyErrands)
async def mine(
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_db),
):
    requested, running = await service.list_mine(db, user)
    return MyErrands(requested=requested, running=running)


@router.get("/{errand_id}", response_model=ErrandOut)
async def detail(
    errand_id: uuid.UUID,
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await service.get_errand(db, user, errand_id)
    except ErrandError as e:
        _raise(e)


@router.get("/{errand_id}/events", response_model=list[ErrandEventOut])
async def events(
    errand_id: uuid.UUID,
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await service.list_events(db, user, errand_id)
    except ErrandError as e:
        _raise(e)


@router.post("/{errand_id}/accept", response_model=ErrandOut)
async def accept(
    errand_id: uuid.UUID,
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
):
    try:
        return await service.accept_errand(db, redis, user, errand_id)
    except ErrandError as e:
        _raise(e)


@router.post("/{errand_id}/pickup", response_model=ErrandOut)
async def pickup(
    errand_id: uuid.UUID,
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
):
    try:
        return await service.pickup_errand(db, redis, user, errand_id)
    except ErrandError as e:
        _raise(e)


@router.post("/{errand_id}/deliver", response_model=ErrandOut)
async def deliver(
    errand_id: uuid.UUID,
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
):
    try:
        return await service.deliver_errand(db, redis, user, errand_id)
    except ErrandError as e:
        _raise(e)


@router.post("/{errand_id}/complete", response_model=ErrandOut)
async def complete(
    errand_id: uuid.UUID,
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
):
    try:
        return await service.complete_errand(db, redis, user, errand_id)
    except ErrandError as e:
        _raise(e)


@router.post("/{errand_id}/cancel", response_model=ErrandOut)
async def cancel(
    errand_id: uuid.UUID,
    body: CancelRequest | None = None,
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
):
    try:
        return await service.cancel_errand(
            db, redis, user, errand_id, body.reason if body else None
        )
    except ErrandError as e:
        _raise(e)


@router.get("/{errand_id}/handoff-secret", response_model=HandoffSecretOut)
async def handoff_secret(
    errand_id: uuid.UUID,
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Assigned runner only, active run only; every read is audited (SECRET_VIEWED)."""
    try:
        return await service.get_handoff_secret(db, user, errand_id)
    except ErrandError as e:
        _raise(e)
