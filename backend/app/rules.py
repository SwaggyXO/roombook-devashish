from dataclasses import dataclass
from datetime import datetime, time, timedelta

from .roles import Role


@dataclass(frozen=True)
class Policy:
    work_start: time = time(9, 30)
    work_end: time = time(18, 30)
    workdays: frozenset[int] = frozenset({0, 1, 2, 3, 4})  # Monday is 0

    slot_step_minutes: int = 15  # start times fall on this grid
    duration_step_minutes: int = 15  # durations are multiples of this
    min_duration_minutes: int = 15
    max_duration_minutes: int = 240

    lunch_start: time = time(13, 0)
    lunch_end: time = time(14, 0)
    lunch_exempt_max_minutes: int = 30

    # The room is cleaned for buffer_minutes after a meeting longer than buffer_threshold_minutes.
    buffer_minutes: int = 15
    buffer_threshold_minutes: int = 60

    # (room name, role) pairs that may not book that room
    restricted: frozenset[tuple[str, Role]] = frozenset({("Board Room", Role.INTERN)})

    suggestion_limit: int = 3

    def __post_init__(self):
        if self.slot_step_minutes <= 0 or self.duration_step_minutes <= 0:
            raise ValueError("step minutes must be positive")
        if self.work_start >= self.work_end:
            raise ValueError("work_start must be before work_end")


DEFAULT_POLICY = Policy()


def room_free_at(start: datetime, end: datetime, policy: Policy = DEFAULT_POLICY) -> datetime:
    if end - start > timedelta(minutes=policy.buffer_threshold_minutes):
        return end + timedelta(minutes=policy.buffer_minutes)
    return end


def can_book(role: Role, room_name: str, policy: Policy = DEFAULT_POLICY) -> bool:
    return (room_name, role) not in policy.restricted
