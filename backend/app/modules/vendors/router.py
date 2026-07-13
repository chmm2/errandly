import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.redis import get_redis
from app.core.security import hash_password
from app.modules.auth.dependencies import require_active_user, require_admin, require_vendor
from app.modules.auth.models import AuthCredential, User
from app.modules.vendors import service
from app.modules.vendors.models import MenuItem, Vendor
from app.modules.vendors.schemas import (
    MenuItemCreate,
    MenuItemOut,
    MenuItemUpdate,
    MenuOut,
    VendorOnboard,
    VendorOut,
    VendorUpdate,
)
from app.modules.vendors.service import VendorError

router = APIRouter(prefix="/vendors", tags=["vendors"])


def _raise(e: VendorError) -> None:
    raise HTTPException(e.status_code, e.message) from e


# ------------------------------------------------------------- student browse

@router.get("", response_model=list[VendorOut])
async def browse(
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_db),
):
    return await service.list_vendors(db, user.campus_id)


@router.get("/me", response_model=VendorOut)
async def my_store(
    user: User = Depends(require_vendor),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await service.get_own_vendor(db, user)
    except VendorError as e:
        _raise(e)


@router.get("/{vendor_id}/menu", response_model=MenuOut)
async def menu(
    vendor_id: uuid.UUID,
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
):
    try:
        return await service.get_menu(db, redis, vendor_id)
    except VendorError as e:
        _raise(e)


# ------------------------------------------------------------- vendor portal

@router.patch("/me", response_model=VendorOut)
async def update_store(
    data: VendorUpdate,
    user: User = Depends(require_vendor),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
):
    try:
        vendor = await service.get_own_vendor(db, user)
    except VendorError as e:
        _raise(e)
    if data.is_open is not None:
        vendor.is_open = data.is_open
    if data.description is not None:
        vendor.description = data.description
    await db.commit()
    await db.refresh(vendor)
    await service.invalidate_menu_cache(redis, vendor.id)
    return vendor


@router.post("/me/menu-items", response_model=MenuItemOut, status_code=status.HTTP_201_CREATED)
async def add_item(
    data: MenuItemCreate,
    user: User = Depends(require_vendor),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
):
    try:
        vendor = await service.get_own_vendor(db, user)
    except VendorError as e:
        _raise(e)
    item = MenuItem(vendor_id=vendor.id, **data.model_dump())
    db.add(item)
    await db.commit()
    await db.refresh(item)
    await service.invalidate_menu_cache(redis, vendor.id)
    return item


@router.patch("/me/menu-items/{item_id}", response_model=MenuItemOut)
async def update_item(
    item_id: uuid.UUID,
    data: MenuItemUpdate,
    user: User = Depends(require_vendor),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
):
    try:
        vendor = await service.get_own_vendor(db, user)
    except VendorError as e:
        _raise(e)
    item = await db.get(MenuItem, item_id)
    if item is None or item.vendor_id != vendor.id:  # ownership, not just role
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Menu item not found.")
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(item, field, value)
    await db.commit()
    await db.refresh(item)
    await service.invalidate_menu_cache(redis, vendor.id)
    return item


@router.delete("/me/menu-items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_item(
    item_id: uuid.UUID,
    user: User = Depends(require_vendor),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
):
    try:
        vendor = await service.get_own_vendor(db, user)
    except VendorError as e:
        _raise(e)
    item = await db.get(MenuItem, item_id)
    if item is None or item.vendor_id != vendor.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Menu item not found.")
    await db.delete(item)
    await db.commit()
    await service.invalidate_menu_cache(redis, vendor.id)


# ------------------------------------------------------------ admin onboarding

@router.post("/onboard", response_model=VendorOut, status_code=status.HTTP_201_CREATED)
async def onboard_vendor(
    data: VendorOnboard,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """No vendor self-signup: an admin creates the account + store together.
    The account is ACTIVE immediately (the admin IS the verification)."""
    existing = await db.scalar(select(User).where(User.email == data.owner_email))
    if existing is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "That email already has an account.")
    owner = User(
        campus_id=admin.campus_id,
        student_id=None,
        email=data.owner_email,
        display_name=data.owner_display_name,
        role="VENDOR",
        account_status="ACTIVE",
    )
    db.add(owner)
    await db.flush()
    db.add(AuthCredential(user_id=owner.id, password_hash=hash_password(data.owner_password)))
    vendor = Vendor(
        campus_id=admin.campus_id,
        owner_user_id=owner.id,
        name=data.name,
        category=data.category,
        description=data.description,
    )
    db.add(vendor)
    await db.commit()
    await db.refresh(vendor)
    return vendor
