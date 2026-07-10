import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Category = Literal["FOOD", "GROCERY", "PARCEL", "STATIONERY", "PHARMACY", "CUSTOM"]

CATALOG_CATEGORIES = {"FOOD", "GROCERY", "STATIONERY", "PHARMACY"}


class ErrandCreate(BaseModel):
    category: Category
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
        return self


class CancelRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=500)


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
