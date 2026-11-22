from dataclasses import dataclass
from datetime import datetime, time

import pytest

from app.roles import Role
from app.rules import DEFAULT_POLICY, Policy, can_book, room_free_at
from app.scheduling import Violation, slot_violations

MONDAY = "2026-12-07"
SATURDAY = "2026-12-05"


def at(hhmm, day=MONDAY):
    return datetime.fromisoformat(f"{day}T{hhmm}")


@dataclass(frozen=True)
class Booked:
    start: datetime
    end: datetime
    room_free_at: datetime


def booked(start, end):
    return Booked(at(start), at(end), room_free_at(at(start), at(end)))


def check(
    start,
    end,
    *,
    day=MONDAY,
    end_day=None,
    room="Focus Room",
    role=Role.EMPLOYEE,
    room_bookings=(),
    people_bookings=(),
    policy=DEFAULT_POLICY,
):
    return slot_violations(
        at(start, day),
        at(end, end_day or day),
        room_name=room,
        requester_role=role,
        room_bookings=room_bookings,
        people_bookings=people_bookings,
        policy=policy,
    )


def test_valid_slot_has_no_violations():
    assert check("10:00", "11:00") == []


@pytest.mark.parametrize(
    "start, end, expected",
    [
        ("10:00", "10:20", [Violation.DURATION]),
        ("10:00", "10:00", [Violation.DURATION]),
        ("10:00", "10:15", []),
        ("09:30", "13:30", [Violation.LUNCH]),
        ("09:30", "13:45", [Violation.DURATION, Violation.LUNCH]),
    ],
)
def test_duration_is_a_multiple_of_15_between_15_and_240(start, end, expected):
    assert check(start, end) == expected


def test_start_must_be_on_the_15_minute_grid():
    assert check("10:05", "11:05") == [Violation.OFF_GRID]


def test_non_workday_is_rejected():
    assert check("10:00", "11:00", day=SATURDAY) == [Violation.NON_WORKDAY]


@pytest.mark.parametrize(
    "start, end, expected",
    [
        ("09:15", "10:15", [Violation.OUTSIDE_HOURS]),
        ("18:00", "18:45", [Violation.OUTSIDE_HOURS]),
        ("17:45", "18:30", []),
        ("09:30", "10:00", []),
    ],
)
def test_meeting_must_fit_working_hours(start, end, expected):
    assert check(start, end) == expected


def test_meeting_ending_on_the_next_day_is_outside_hours():
    assert check("23:45", "00:15", end_day="2026-12-08") == [Violation.OUTSIDE_HOURS]


@pytest.mark.parametrize(
    "start, end, expected",
    [
        ("12:30", "13:30", [Violation.LUNCH]),
        ("12:45", "13:45", [Violation.LUNCH]),
        ("13:00", "13:30", []),
        ("12:00", "13:00", []),
        ("14:00", "15:00", []),
    ],
)
def test_meeting_over_30_minutes_cannot_overlap_lunch(start, end, expected):
    assert check(start, end) == expected


def test_buffer_does_not_count_towards_lunch():
    assert check("11:45", "13:00") == []


def test_lunch_exemption_stops_above_30_minutes():
    assert check("13:00", "13:45") == [Violation.LUNCH]


HIRING_PANEL = booked("10:00", "11:30")


@pytest.mark.parametrize(
    "start, end, expected",
    [
        ("11:30", "12:00", [Violation.ROOM_BUSY]),
        ("11:45", "12:15", []),
        ("09:30", "10:00", []),
    ],
)
def test_room_is_busy_until_its_cleaning_buffer_ends(start, end, expected):
    assert check(start, end, room_bookings=[HIRING_PANEL]) == expected


RETRO = booked("17:30", "18:30")


@pytest.mark.parametrize(
    "start, end, expected",
    [
        ("16:15", "17:30", [Violation.ROOM_BUSY]),
        ("16:30", "17:30", []),
    ],
)
def test_new_meetings_own_buffer_counts_against_next_booking(start, end, expected):
    assert check(start, end, room_bookings=[RETRO]) == expected


@pytest.mark.parametrize(
    "start, end, expected",
    [
        ("10:30", "11:00", [Violation.ATTENDEE_BUSY]),
        ("11:00", "11:30", []),
        ("09:30", "10:00", []),
    ],
)
def test_attendee_cannot_be_in_two_meetings(start, end, expected):
    assert check(start, end, people_bookings=[booked("10:00", "11:00")]) == expected


@pytest.mark.parametrize(
    "role, room, expected",
    [
        (Role.INTERN, "Board Room", [Violation.RESTRICTED_ROOM]),
        (Role.MANAGER, "Board Room", []),
        (Role.INTERN, "Huddle", []),
    ],
)
def test_board_room_is_closed_to_interns(role, room, expected):
    assert check("10:00", "11:00", room=room, role=role) == expected


def test_all_violations_are_reported_in_a_stable_order():
    assert check("13:00", "14:00", day=SATURDAY) == [Violation.NON_WORKDAY, Violation.LUNCH]
    assert check(
        "09:15",
        "10:15",
        room="Board Room",
        role=Role.INTERN,
        people_bookings=[booked("10:00", "11:00")],
    ) == [Violation.OUTSIDE_HOURS, Violation.ATTENDEE_BUSY, Violation.RESTRICTED_ROOM]


def test_custom_policy_moves_lunch():
    policy = Policy(lunch_start=time(12), lunch_end=time(13))
    assert check("12:00", "13:00", policy=policy) == [Violation.LUNCH]
    assert check("13:00", "14:00", policy=policy) == []


def test_can_book():
    assert not can_book(Role.INTERN, "Board Room")
    assert can_book(Role.MANAGER, "Board Room")
    assert can_book(Role.INTERN, "Huddle")


def test_can_book_with_custom_policy():
    assert can_book(Role.INTERN, "Board Room", Policy(restricted=frozenset()))


@pytest.mark.parametrize(
    "start, end, busy",
    [
        ("10:00", "11:15", booked("11:15", "11:45")),
        ("11:00", "11:30", booked("09:30", "11:00")),
    ],
)
def test_buffer_does_not_block_people(start, end, busy):
    assert check(start, end, people_bookings=[busy]) == []


def test_buffer_may_run_past_closing_time():
    assert check("17:15", "18:30") == []
