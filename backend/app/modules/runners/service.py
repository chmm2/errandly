import uuid
from datetime import UTC, datetime

from redis.asyncio import Redis
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.models import User
from app.modules.errands.models import Errand
from app.modules.runners.models import RunnerProfile
from app.modules.runners.schemas import AvailabilityUpdate, LocationUpdate

GEO_KEY_PREFIX = "runners:geo:"  # one GEO set per campus
ACTIVE_RUN_STATUSES = ("ACCEPTED", "IN_PROGRESS")
# Skip DB writes for heartbeats arriving faster than this (Redis GEO is
# still refreshed — it's cheap; Postgres isn't).
LOCATION_DB_WRITE_INTERVAL_SECONDS = 5


def geo_key(campus_id: uuid.UUID) -> str:
    return f"{GEO_KEY_PREFIX}{campus_id}"


async def get_or_create_profile(db: AsyncSession, user: User) -> RunnerProfile:
    profile = await db.get(RunnerProfile, user.id)
    if profile is None:
        profile = RunnerProfile(user_id=user.id, campus_id=user.campus_id)
        db.add(profile)
        await db.flush()
    return profile


async def active_load(db: AsyncSession, user_id: uuid.UUID) -> int:
    count = await db.scalar(
        select(func.count())
        .select_from(Errand)
        .where(Errand.runner_id == user_id, Errand.status.in_(ACTIVE_RUN_STATUSES))
    )
    return count or 0


async def set_availability(
    db: AsyncSession, redis: Redis, user: User, data: AvailabilityUpdate
) -> RunnerProfile:
    profile = await get_or_create_profile(db, user)
    profile.is_available = data.is_available
    key = geo_key(user.campus_id)

    if data.is_available:
        profile.last_lat = data.lat
        profile.last_lng = data.lng
        profile.location_updated_at = datetime.now(UTC)
        await redis.geoadd(key, (data.lng, data.lat, str(user.id)))
    else:
        await redis.zrem(key, str(user.id))

    await db.commit()
    await db.refresh(profile)
    return profile


async def update_location(
    db: AsyncSession, redis: Redis, user: User, data: LocationUpdate
) -> RunnerProfile:
    profile = await get_or_create_profile(db, user)

    if profile.is_available:
        await redis.geoadd(geo_key(user.campus_id), (data.lng, data.lat, str(user.id)))

    # Throttle the Postgres write, not the Redis one.
    throttle_key = f"runner:locwrite:{user.id}"
    fresh = await redis.set(throttle_key, "1", nx=True, ex=LOCATION_DB_WRITE_INTERVAL_SECONDS)
    if fresh:
        profile.last_lat = data.lat
        profile.last_lng = data.lng
        profile.location_updated_at = datetime.now(UTC)
        await db.commit()
        await db.refresh(profile)
    return profile


async def nearest_available_runners(
    redis: Redis,
    campus_id: uuid.UUID,
    lat: float,
    lng: float,
    radius_m: int = 3000,
    limit: int = 5,
    exclude: uuid.UUID | None = None,
) -> list[tuple[uuid.UUID, float]]:
    """(runner_id, distance_m) sorted nearest-first, from the Redis GEO index."""
    results = await redis.geosearch(
        geo_key(campus_id),
        longitude=lng,
        latitude=lat,
        radius=radius_m,
        unit="m",
        withdist=True,
        sort="ASC",
        count=limit + (1 if exclude else 0),
    )
    out: list[tuple[uuid.UUID, float]] = []
    for member, dist in results:
        member_id = uuid.UUID(member)
        if exclude and member_id == exclude:
            continue
        out.append((member_id, float(dist)))
    return out[:limit]
