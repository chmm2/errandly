from fastapi import Depends, HTTPException, Request, status
from redis.asyncio import Redis

from app.core.redis import get_redis


class RateLimiter:
    """Redis fixed-window rate limiter, used as a FastAPI dependency.

    INCR the window key; the first hit sets the EXPIRE (atomic enough for a
    fixed window — worst case a race grants one extra request, acceptable
    here). Keyed per client IP so one abuser can't exhaust the window for
    everyone. Fails open if Redis is down: availability of the API matters
    more than strict throttling.
    """

    def __init__(self, times: int, seconds: int, scope: str):
        self.times = times
        self.seconds = seconds
        self.scope = scope

    async def __call__(self, request: Request, redis: Redis = Depends(get_redis)) -> None:
        client_ip = request.client.host if request.client else "unknown"
        key = f"rl:{self.scope}:{client_ip}"
        try:
            count = await redis.incr(key)
            if count == 1:
                await redis.expire(key, self.seconds)
            ttl = await redis.ttl(key)
        except Exception:
            return  # fail open
        if count > self.times:
            retry_after = ttl if ttl > 0 else self.seconds
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS,
                "Too many requests. Slow down.",
                headers={"Retry-After": str(retry_after)},
            )
