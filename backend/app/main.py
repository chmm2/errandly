from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.core.config import settings
from app.core.database import engine
from app.core.redis import redis_client
from app.modules.analytics.router import router as analytics_router
from app.modules.auth.router import router as auth_router
from app.modules.chat.router import router as chat_router
from app.modules.errands.router import router as errands_router
from app.modules.ledger.router import router as ledger_router
from app.modules.notifications.router import router as notifications_router
from app.modules.realtime.router import router as realtime_router
from app.modules.runners.router import router as runners_router
from app.modules.vendors.router import router as vendors_router

app = FastAPI(title="Errandly API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(errands_router)
app.include_router(runners_router)
app.include_router(realtime_router)
app.include_router(notifications_router)
app.include_router(analytics_router)
app.include_router(vendors_router)
app.include_router(ledger_router)
app.include_router(chat_router)


@app.get("/health", tags=["system"])
async def health():
    """Liveness + dependency check for DB and Redis."""
    checks = {"db": "down", "redis": "down"}
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        checks["db"] = "up"
    except Exception:
        pass
    try:
        if await redis_client.ping():
            checks["redis"] = "up"
    except Exception:
        pass
    status = "ok" if all(v == "up" for v in checks.values()) else "degraded"
    return {"status": status, "checks": checks, "environment": settings.environment}
