import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

VendorCategory = Literal["FOOD", "GROCERY", "STATIONERY", "PHARMACY"]


class VendorOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    category: str
    description: str | None
    is_open: bool


class VendorUpdate(BaseModel):
    is_open: bool | None = None
    description: str | None = Field(default=None, max_length=300)


class MenuItemCreate(BaseModel):
    section: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=120)
    price: float = Field(ge=0, le=100000)
    position: int = Field(default=0, ge=0)


class MenuItemUpdate(BaseModel):
    section: str | None = Field(default=None, min_length=1, max_length=80)
    name: str | None = Field(default=None, min_length=1, max_length=120)
    price: float | None = Field(default=None, ge=0, le=100000)
    is_available: bool | None = None
    position: int | None = Field(default=None, ge=0)


class MenuItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    section: str
    name: str
    price: float
    is_available: bool
    position: int


class MenuOut(BaseModel):
    vendor: VendorOut
    items: list[MenuItemOut]
    stale: bool = False  # true when served from the stale-fallback cache


class VendorOnboard(BaseModel):
    """Admin creates the vendor account + store in one call."""

    name: str = Field(min_length=1, max_length=120)
    category: VendorCategory
    description: str | None = Field(default=None, max_length=300)
    owner_email: EmailStr
    owner_display_name: str = Field(min_length=1, max_length=120)
    owner_password: str = Field(min_length=8, max_length=128)
