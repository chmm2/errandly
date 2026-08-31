import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class EarningsSummary(BaseModel):
    """Runner-facing: what I made. Unchanged shape so the earnings card
    on the runner dashboard keeps working."""

    balance: float
    week_total: float
    week_runs: int


class LedgerEntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    errand_id: uuid.UUID | None
    entry_type: str
    direction: str
    amount: float
    memo: str | None
    created_at: datetime


class WalletOut(BaseModel):
    """Balance plus what is currently locked in escrow.

    `available` is what the wallet can actually spend right now: escrowed money
    has already left the balance, so showing it separately explains where it
    went rather than leaving a hole the requester has to guess at.
    """

    balance: float
    held: float
    recent: list[LedgerEntryOut]


class TopUpRequest(BaseModel):
    amount: float = Field(gt=0, le=100000)


class EscrowOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    errand_id: uuid.UUID
    items_total: float
    reward: float
    collect_amount: float
    buffer: float
    amount: float
    released_amount: float
    status: str
    created_at: datetime
    settled_at: datetime | None
