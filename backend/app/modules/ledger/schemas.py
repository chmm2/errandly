import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class EarningsSummary(BaseModel):
    balance: float
    week_total: float
    week_runs: int


class TopupRequest(BaseModel):
    amount: float = Field(gt=0, le=100000)


class LedgerEntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    seq: int
    entry_type: str
    amount: float
    errand_id: uuid.UUID | None
    created_at: datetime


class WalletOut(BaseModel):
    balance: float
    entries: list[LedgerEntryOut]


class QuoteRequest(BaseModel):
    drop_lat: float = Field(ge=-90, le=90)
    drop_lng: float = Field(ge=-180, le=180)
    item_total: float = Field(default=0, ge=0, le=100000)
    tip: float = Field(default=0, ge=0, le=10000)


class QuoteOut(BaseModel):
    item_total: float
    runner_fee: float
    convenience_fee: float
    total: float


class VerifyOut(BaseModel):
    campus_id: str
    intact: bool
    entries: int
    broken_seq: int | None = None
    reason: str | None = None
