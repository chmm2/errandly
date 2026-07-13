import json
import logging
import uuid

from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.models import User
from app.modules.vendors.models import MenuItem, Vendor

logger = logging.getLogger(__name__)

MENU_CACHE_PREFIX = "menu:"          # fresh copy, short TTL
MENU_STALE_PREFIX = "menu:stale:"    # long-lived fallback copy
MENU_CACHE_TTL = 300


class VendorError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


async def get_own_vendor(db: AsyncSession, user: User) -> Vendor:
    """Ownership, not just role: a VENDOR user manages exactly their store."""
    vendor = await db.scalar(select(Vendor).where(Vendor.owner_user_id == user.id))
    if vendor is None:
        raise VendorError("No store is linked to your account.", 404)
    return vendor


def _menu_payload(vendor: Vendor, items: list[MenuItem]) -> dict:
    return {
        "vendor": {
            "id": str(vendor.id),
            "name": vendor.name,
            "category": vendor.category,
            "description": vendor.description,
            "is_open": vendor.is_open,
        },
        "items": [
            {
                "id": str(i.id),
                "section": i.section,
                "name": i.name,
                "price": float(i.price),
                "is_available": i.is_available,
                "position": i.position,
            }
            for i in items
        ],
    }


async def invalidate_menu_cache(redis: Redis, vendor_id: uuid.UUID) -> None:
    """Cache invalidation ON WRITE: a sold-out toggle must show instantly,
    not after a TTL. (Only the fresh key dies — the stale copy survives as
    the degradation fallback and gets replaced on the next successful read.)"""
    await redis.delete(f"{MENU_CACHE_PREFIX}{vendor_id}")


async def get_menu(db: AsyncSession, redis: Redis, vendor_id: uuid.UUID) -> dict:
    """Cache-aside with fallback-to-stale.

    Fresh key (5min TTL) absorbs the read traffic; every DB read also
    refreshes a no-TTL stale copy. If Postgres is slow/down, a slightly old
    menu beats an error page.
    """
    fresh_key = f"{MENU_CACHE_PREFIX}{vendor_id}"
    cached = await redis.get(fresh_key)
    if cached:
        return json.loads(cached)

    try:
        vendor = await db.get(Vendor, vendor_id)
        if vendor is None:
            raise VendorError("Store not found.", 404)
        items = list(
            await db.scalars(
                select(MenuItem)
                .where(MenuItem.vendor_id == vendor_id)
                .order_by(MenuItem.section, MenuItem.position, MenuItem.name)
            )
        )
    except VendorError:
        raise
    except Exception:
        stale = await redis.get(f"{MENU_STALE_PREFIX}{vendor_id}")
        if stale:
            logger.warning("serving STALE menu for %s (db unavailable)", vendor_id)
            payload = json.loads(stale)
            payload["stale"] = True
            return payload
        raise

    payload = _menu_payload(vendor, items)
    body = json.dumps(payload)
    await redis.set(fresh_key, body, ex=MENU_CACHE_TTL)
    await redis.set(f"{MENU_STALE_PREFIX}{vendor_id}", body)
    return payload


async def list_vendors(db: AsyncSession, campus_id: uuid.UUID) -> list[Vendor]:
    return list(
        await db.scalars(
            select(Vendor)
            .where(Vendor.campus_id == campus_id)
            .order_by(Vendor.is_open.desc(), Vendor.name)
        )
    )
