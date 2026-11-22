from pydantic import BaseModel, ConfigDict, Field, model_validator

from .office_time import OfficeTime, OfficeTimeOut
from .roles import Role


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
