import datetime as dt

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .office_time import OfficeTime, OfficeTimeOut
from .roles import Role
from .rules import duration_error


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    role: Role


class RoomIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    capacity: int = Field(gt=0, le=100)


class RoomOut(RoomIn):
    model_config = ConfigDict(from_attributes=True)

    id: int


class RoomAccessOut(RoomOut):
    bookable: bool | None = None


class BookingIn(BaseModel):
    room_id: int
    creator_id: int
    title: str = Field(default="", max_length=200)
    attendee_ids: list[int] = Field(default_factory=list)
    start: OfficeTime
    end: OfficeTime

    @model_validator(mode="after")
    def check_order(self) -> "BookingIn":
        if self.end <= self.start:
            raise ValueError("end must be after start")
        return self


class BookingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    room: RoomOut
    creator_id: int
    attendees: list[UserOut]
    start: OfficeTimeOut
    end: OfficeTimeOut


class SuggestIn(BaseModel):
    requester_id: int
    attendee_ids: list[int] = Field(default_factory=list)
    duration_minutes: int
    date: dt.date
    after: OfficeTime | None = None

    @field_validator("duration_minutes")
    @classmethod
    def check_duration(cls, value: int) -> int:
        error = duration_error(value)
        if error:
            raise ValueError(error)
        return value


class SlotOut(BaseModel):
    start: OfficeTimeOut
    end: OfficeTimeOut


class SuggestOut(BaseModel):
    slots: list[SlotOut]
    has_more: bool
