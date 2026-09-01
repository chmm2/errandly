import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Category = Literal["FOOD", "GROCERY", "PARCEL", "STATIONERY", "PHARMACY", "CUSTOM"]

CATALOG_CATEGORIES = {"FOOD", "GROCERY", "STATIONERY", "PHARMACY"}


class OrderItemIn(BaseModel):
    menu_item_id: uuid.UUID
    quantity: int = Field(ge=1, le=20)


class ListItemIn(BaseModel):
    """A shopping-list line.

    `reference_id` is set when the requester picked the item off the admin's
    non-MRP price list rather than typing a name nobody has priced. The server
    re-reads the price from that row - the client never sends an amount, so a
    tampered request cannot inflate what gets held.
    """

    name: str = Field(min_length=1, max_length=120)
    quantity: int = Field(default=1, ge=1, le=99)
    note: str | None = Field(default=None, max_length=200)
    reference_id: uuid.UUID | None = None


class ErrandCreate(BaseModel):
    category: Category
    # Catalog orders: which store + what items (server revalidates + reprices)
    vendor_id: uuid.UUID | None = None
    items: list[OrderItemIn] = Field(default_factory=list, max_length=20)
    # Shopping-list orders: hand-typed lines the runner buys off a real shelf.
    list_items: list[ListItemIn] = Field(default_factory=list, max_length=30)
    title: str = Field(min_length=3, max_length=200)
    notes: str | None = Field(default=None, max_length=2000)
    pickup_label: str = Field(min_length=2, max_length=200)
    drop_lat: float = Field(ge=-90, le=90)
    drop_lng: float = Field(ge=-180, le=180)
    drop_label: str | None = Field(default=None, max_length=200)
    reward: float = Field(ge=0, le=10000)
    # How long the requester will wait for a runner before the errand expires.
    wait_minutes: int = Field(default=30, ge=5, le=120)
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
        if (self.items or self.list_items) and self.category not in CATALOG_CATEGORIES:
            raise ValueError("Items only apply to store orders and shopping lists.")
        if self.items and self.vendor_id is None:
            raise ValueError("Menu items need a vendor_id.")
        if self.items and self.list_items:
            raise ValueError("Use menu items or a hand-typed list, not both.")
        return self


class CancelRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=500)


class RateRequest(BaseModel):
    stars: int = Field(ge=1, le=5)
    comment: str | None = Field(default=None, max_length=500)


class RunnerSummary(BaseModel):
    """Who's running the errand — shown to the two parties on the tracking
    page. Phone is revealed only during an active run so the requester can
    call the runner; it goes null again once the errand is done."""

    id: uuid.UUID
    display_name: str
    reputation_score: float
    rating_count: int
    trips_completed: int = 0
    photo_url: str | None = None
    phone: str | None = None


class ConnectionOut(BaseModel):
    """How the viewer is connected to the other party on an errand.

    `degree` is friendship hops: 1 = your friend, 2 = friend of a friend, and
    so on. None means no path within the traversal limit — a stranger.
    `label` is the short badge form (1st/2nd/3rd/R), computed server-side so
    every client renders the same thing.
    """

    degree: int | None = None
    label: str = "R"
    via: str | None = None  # display name of the friend who connects you
    trust: float = 0.0


class PickupIn(BaseModel):
    """What the runner paid, declared as they mark the errand picked up.

    Required, not optional. The escrow headroom exists so a runner who paid
    more than the estimate is still made whole, and that is unusable unless
    someone says what was actually paid - without it the platform can only
    reimburse its own guess. Declaring it at pickup rather than at delivery
    also means it is on the record while the runner is still standing at the
    counter, before the amount is worth arguing about.
    """

    amount_spent: float = Field(ge=0, le=100000)


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
    # None until the runner declares it at pickup.
    amount_spent: float | None = None
    has_handoff_secret: bool = False
    distance_m: float | None = None
    # Runner's last known position — populated on the detail endpoint only,
    # for the requester/runner while the run is active (tracking page).
    runner_lat: float | None = None
    runner_lng: float | None = None
    runner: RunnerSummary | None = None
    vendor_id: uuid.UUID | None = None
    items: list["ErrandItemOut"] = []
    items_total: float = 0
    rated: bool = False
    connection: ConnectionOut | None = None
    status: str
    version: int
    expires_at: datetime | None = None
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
    # Set when the line was priced off the admin non-MRP list - which is also
    # what made it eligible for escrow headroom, so the clients need it to
    # explain the hold.
    reference_id: uuid.UUID | None = None
    name_snapshot: str
    unit_price_snapshot: float | None
    quantity: int
    is_available: bool = True
    note: str | None = None


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
