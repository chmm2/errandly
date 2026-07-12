import uuid

from pydantic import BaseModel, ConfigDict, Field, model_validator


class SlotCreate(BaseModel):
    day_of_week: int = Field(ge=0, le=6, description="0 = Monday")
    start_minute: int = Field(ge=0, lt=1440)
    end_minute: int = Field(gt=0, le=1440)
    label: str = Field(min_length=1, max_length=120)

    @model_validator(mode="after")
    def end_after_start(self):
        if self.end_minute <= self.start_minute:
            raise ValueError("end_minute must be after start_minute")
        return self


class SlotOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    day_of_week: int
    start_minute: int
    end_minute: int
    label: str
