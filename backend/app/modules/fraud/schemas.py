import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ClaimLineIn(BaseModel):
    """One line of what the runner actually paid at the counter."""

    name: str = Field(min_length=1, max_length=120)
    unit_price: float = Field(ge=0, le=10000)
    quantity: int = Field(default=1, ge=1, le=50)


class ClaimSubmission(BaseModel):
    lines: list[ClaimLineIn] = Field(min_length=1, max_length=20)


class ClaimOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    errand_id: uuid.UUID
    raw_name: str
    item_key: str
    claimed_unit_price: float
    quantity: int
    reference_snapshot: float | None
    threshold_snapshot: float | None
    delta_pct: float | None
    delta_abs: float | None
    verdict: str
    eligible_amount: float
    created_at: datetime


class ClaimResult(BaseModel):
    """What the runner sees back after reporting prices.

    `withheld` is stated plainly rather than buried: a runner who is about to
    be paid less than they asked for should find out here, at the counter, not
    when a smaller number lands in their wallet hours later.
    """

    claims: list[ClaimOut]
    total_claimed: float
    total_eligible: float
    withheld: float
    message: str | None = None


class ReferencePriceIn(BaseModel):
    item_key: str | None = Field(default=None, max_length=120)
    display_name: str = Field(min_length=1, max_length=120)
    reference_price: float = Field(gt=0, le=10000)
    band_min: float = Field(gt=0, le=10000)
    band_max: float = Field(gt=0, le=10000)
    # Rupees over the reference before a claim is flagged outright.
    tolerance_abs: float = Field(default=20.0, gt=0, le=1000)

    @model_validator(mode="after")
    def coherent_band(self):
        if self.band_max < self.band_min:
            raise ValueError("band_max must be at least band_min.")
        if not (self.band_min <= self.reference_price <= self.band_max):
            raise ValueError("reference_price must sit inside the band.")
        return self


class ReferencePriceUpdate(BaseModel):
    display_name: str | None = Field(default=None, max_length=120)
    reference_price: float | None = Field(default=None, gt=0, le=10000)
    band_min: float | None = Field(default=None, gt=0, le=10000)
    band_max: float | None = Field(default=None, gt=0, le=10000)
    tolerance_abs: float | None = Field(default=None, gt=0, le=1000)


class ReferencePriceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    item_key: str
    display_name: str
    reference_price: float
    band_min: float
    band_max: float
    tolerance_abs: float
    source: str
    sample_count: int
    last_estimated_at: datetime | None
    updated_at: datetime


class ProposalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    reference_price_id: uuid.UUID
    proposed_price: float
    proposed_band_min: float
    proposed_band_max: float
    observed_median: float
    sample_count: int
    reason: str
    status: str
    created_at: datetime


class FlagOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    errand_id: uuid.UUID | None
    claim_id: uuid.UUID | None
    rule: str
    severity: int
    details: dict[str, Any] | None
    status: str
    created_at: datetime
    reviewed_at: datetime | None


class FlagReview(BaseModel):
    uphold: bool
    note: str | None = Field(default=None, max_length=500)


class StrikeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    level: int
    action: str
    reason: str
    expires_at: datetime | None
    lifted_at: datetime | None
    created_at: datetime


class StandingOut(BaseModel):
    """A runner's own record. Deliberately visible to them: someone being
    penalised by a system is owed a way to see what it thinks they did."""

    flags_in_window: int
    strikes: list[StrikeOut]
    blocked_until: datetime | None
    next_action_at: int | None = None
