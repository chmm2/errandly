import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Category = Literal["FOOD", "GROCERY", "PARCEL", "STATIONERY", "PHARMACY", "CUSTOM"]

CATALOG_CATEGORIES = {"FOOD", "GROCERY", "STATIONERY", "PHARMACY"}


class OrderItemIn(BaseModel):
    menu_item_id: uuid.UUID
    quantity: int = Field(ge=1, le=20)


class ErrandCreate(BaseModel):
    category: Category
    # Catalog orders: which store + what items (server revalidates + reprices)
    vendor_id: uuid.UUID | None = None
    items: list[OrderItemIn] = Field(default_factory=list, max_length=20)
    title: str = Field(min_length=3, max_length=200)
    notes: str | None = Field(default=None, max_length=2000)
    pickup_label: str = Field(min_length=2, max_length=200)
    drop_lat: float = Field(ge=-90, le=90)
    drop_lng: float = Field(ge=-180, le=180)
    drop_label: str | None = Field(default=None, max_length=200)
    reward: float = Field(ge=0, le=10000)
    # Verified handoff (gate/parcel pickups only)
    external_ref: str | None = Field(default=None, max_length=100)
    otp: str | None = Field(default=None, min_length=3, max_length=12)
    collect_amount: float = Field(default=0, ge=0, le=10000)

    @model_validator(mode="after")
    def handoff_fields_only_for_pickups(self):
        if self.category in CATALOG_CATEGORIES and (self.external_ref or self.otp):
            raise ValueError(
                "Order number / OTP only apply to Custom (gate) and Parcel pickups."
            )
        if self.items and self.category not in CATALOG_CATEGORIES:
            raise ValueError("Menu items only apply to store orders.")
        if self.items and self.vendor_id is None:
            raise ValueError("Menu items need a vendor_id.")
        return self


class CancelRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=500)


class RateRequest(BaseModel):
    stars: int = Field(ge=1, le=5)
    comment: str | None = Field(default=None, max_length=500)


class ErrandOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    campus_id: uuid.UUID
    requester_id: uuid.UUID
    runner_id: uuid.UUID | None
    category: str
    title: str
    notes: str | None
    pickup_label: str
    drop_lat: float
    drop_lng: float
    drop_label: str | None
    reward: float
    fulfillment_type: str
    collect_amount: float
    has_handoff_secret: bool = False
    distance_m: float | None = None
    # Runner's last known position — populated on the detail endpoint only,
    # for the requester/runner while the run is active (tracking page).
    runner_lat: float | None = None
    runner_lng: float | None = None
    vendor_id: uuid.UUID | None = None
    items: list["ErrandItemOut"] = []
    items_total: float = 0
    status: str
    version: int
    accepted_at: datetime | None
    delivered_at: datetime | None
    completed_at: datetime | None
    cancelled_at: datetime | None
    created_at: datetime


class ErrandFeed(BaseModel):
    items: list[ErrandOut]
    limit: int
    offset: int
    total: int


class MyErrands(BaseModel):
    requested: list[ErrandOut]
    running: list[ErrandOut]


class ErrandItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    menu_item_id: uuid.UUID | None
    name_snapshot: str
    unit_price_snapshot: float
    quantity: int


class HandoffSecretOut(BaseModel):
    """Disclosed only to the assigned runner; every read is audited."""

    otp: str | None
    external_ref: str | None
    collect_amount: float


class ErrandEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    actor_id: uuid.UUID | None
    event_type: str
    payload: dict[str, Any] | None
    created_at: datetime
