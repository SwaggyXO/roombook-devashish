from datetime import datetime, timedelta, timezone
from typing import Annotated

from pydantic import AfterValidator, PlainSerializer

from .rules import DEFAULT_POLICY

# IST has no DST, so a fixed offset is enough (and needs no tz database on Windows).
IST = timezone(timedelta(hours=5, minutes=30))


def to_office_time(value: datetime) -> datetime:
    """Naive IST wall time, which is what the database stores."""
    if value.tzinfo is not None:
        try:
            value = value.astimezone(IST).replace(tzinfo=None)
        except OverflowError:
            raise ValueError("time is out of range")
    if value.second or value.microsecond:
        raise ValueError("time must not have seconds (in IST)")
    step = DEFAULT_POLICY.slot_step_minutes
    if value.minute % step:
        raise ValueError(f"time must be on a {step}-minute boundary (in IST)")
    return value


def to_iso_ist(value: datetime) -> str:
    aware = value.astimezone(IST) if value.tzinfo else value.replace(tzinfo=IST)
    return aware.isoformat()


OfficeTimeOut = Annotated[datetime, PlainSerializer(to_iso_ist, return_type=str, when_used="json")]
OfficeTime = Annotated[OfficeTimeOut, AfterValidator(to_office_time)]
