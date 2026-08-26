import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class FriendOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    display_name: str
    photo_url: str | None = None
    reputation_score: float


class PendingRequestOut(BaseModel):
    id: uuid.UUID  # the friendship row, i.e. what to accept/decline
    from_user: FriendOut
    created_at: datetime


class FriendRequestCreate(BaseModel):
    user_id: uuid.UUID


class RespondRequest(BaseModel):
    accept: bool


class SearchResultOut(FriendOut):
    """A student you might add, plus where they already sit relative to you."""

    relationship: str  # NONE | PENDING_OUT | PENDING_IN | FRIENDS | BLOCKED
    mutual_friends: int = 0
