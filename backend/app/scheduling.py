from datetime import date, datetime, timedelta
from enum import StrEnum
from typing import Protocol, Sequence

from .roles import Role
from .rules import DEFAULT_POLICY, Policy, can_book, room_free_at


def overlaps(a_start: datetime, a_end: datetime, b_start: datetime, b_end: datetime) -> bool:
    """True if the time range a overlaps the time range b."""
    return a_start < b_end and b_start < a_end


class BookedSlot(Protocol):
    @property
    def start(self) -> datetime: ...

    @property
    def end(self) -> datetime: ...

    @property
    def room_free_at(self) -> datetime: ...


class Violation(StrEnum):
    DURATION = "duration"
    OFF_GRID = "off_grid"
    NON_WORKDAY = "non_workday"
    OUTSIDE_HOURS = "outside_hours"
    LUNCH = "lunch"
    ROOM_BUSY = "room_busy"
    ATTENDEE_BUSY = "attendee_busy"
    RESTRICTED_ROOM = "restricted_room"


def slot_violations(
    start: datetime,
    end: datetime,
    *,
    room_name: str,
    requester_role: Role,
    room_bookings: Sequence[BookedSlot],
    people_bookings: Sequence[BookedSlot],
    policy: Policy = DEFAULT_POLICY,
) -> list[Violation]:
    """Every rule the slot breaks, in a fixed order. An empty list means it can be booked.

    start and end are naive IST times. room_bookings are the room's existing bookings.
    people_bookings are every booking of the requester or any attendee, in any room.
    """
    violations = []
    duration = end - start

    step = timedelta(minutes=policy.duration_step_minutes)
    min_duration = timedelta(minutes=policy.min_duration_minutes)
    max_duration = timedelta(minutes=policy.max_duration_minutes)
    if duration % step or not min_duration <= duration <= max_duration:
        violations.append(Violation.DURATION)

    if start.minute % policy.slot_step_minutes or start.second or start.microsecond:
        violations.append(Violation.OFF_GRID)

    if start.weekday() not in policy.workdays:
        violations.append(Violation.NON_WORKDAY)

    if (
        start.time() < policy.work_start
        or end.date() != start.date()
        or end.time() > policy.work_end
    ):
        violations.append(Violation.OUTSIDE_HOURS)

    lunch_start = datetime.combine(start.date(), policy.lunch_start)
    lunch_end = datetime.combine(start.date(), policy.lunch_end)
    lunch_exempt = duration <= timedelta(minutes=policy.lunch_exempt_max_minutes)
    if not lunch_exempt and overlaps(start, end, lunch_start, lunch_end):
        violations.append(Violation.LUNCH)

    room_window_end = room_free_at(start, end, policy)
    if any(overlaps(start, room_window_end, b.start, b.room_free_at) for b in room_bookings):
        violations.append(Violation.ROOM_BUSY)

    if any(overlaps(start, end, b.start, b.end) for b in people_bookings):
        violations.append(Violation.ATTENDEE_BUSY)

    if not can_book(requester_role, room_name, policy):
        violations.append(Violation.RESTRICTED_ROOM)

    return violations


def find_slots(
    day: date,
    duration_minutes: int,
    *,
    room_name: str,
    requester_role: Role,
    room_bookings: Sequence[BookedSlot],
    people_bookings: Sequence[BookedSlot],
    policy: Policy = DEFAULT_POLICY,
) -> list[tuple[datetime, datetime]]:
    """The earliest valid slots on the day, up to policy.suggestion_limit."""
    duration = timedelta(minutes=duration_minutes)
    step = timedelta(minutes=policy.slot_step_minutes)
    day_end = datetime.combine(day, policy.work_end)
    start = datetime.combine(day, policy.work_start)
    slots = []
    while start + duration <= day_end and len(slots) < policy.suggestion_limit:
        end = start + duration
        if not slot_violations(
            start,
            end,
            room_name=room_name,
            requester_role=requester_role,
            room_bookings=room_bookings,
            people_bookings=people_bookings,
            policy=policy,
        ):
            slots.append((start, end))
        start += step
    return slots
