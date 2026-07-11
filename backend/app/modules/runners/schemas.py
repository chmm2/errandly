from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator


class LocationUpdate(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)


class AvailabilityUpdate(BaseModel):
    is_available: bool
    lat: float | None = Field(default=None, ge=-90, le=90)
    lng: float | None = Field(default=None, ge=-180, le=180)

    @model_validator(mode="after")
    def location_required_when_going_available(self):
        if self.is_available and (self.lat is None or self.lng is None):
            raise ValueError("Going available requires a current location (lat/lng).")
        return self


class RunnerProfileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    is_available: bool
    max_load: int
    active_load: int = 0
    last_lat: float | None
    last_lng: float | None
    location_updated_at: datetime | None
