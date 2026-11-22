from dataclasses import dataclass
from datetime import date, datetime, timedelta

from hypothesis import given, settings
from hypothesis import strategies as st

from app.roles import Role
from app.rules import DEFAULT_POLICY, Policy, room_free_at
from app.scheduling import find_slots, slot_violations

MONDAY = date(2026, 12, 7)
SATURDAY = date(2026, 12, 5)
WEEKDAYS = [date(2026, 12, 7 + i) for i in range(5)]
ROOMS = ["Focus Room", "Board Room", "Huddle"]
MINUTE = timedelta(minutes=1)
DURATIONS = range(
    DEFAULT_POLICY.min_duration_minutes,
    DEFAULT_POLICY.max_duration_minutes + 1,
    DEFAULT_POLICY.duration_step_minutes,
)


@dataclass(frozen=True)
class Booked:
    start: datetime
    end: datetime
    room_free_at: datetime


def booked(start, end, day=MONDAY):
    s = datetime.fromisoformat(f"{day}T{start}")
    e = datetime.fromisoformat(f"{day}T{end}")
    return Booked(s, e, room_free_at(s, e))


def slots(day=MONDAY, minutes=30, *, room="Focus Room", role=Role.EMPLOYEE,
          room_bookings=(), people_bookings=(), policy=DEFAULT_POLICY):
    return find_slots(
        day,
        minutes,
        room_name=room,
        requester_role=role,
        room_bookings=room_bookings,
        people_bookings=people_bookings,
        policy=policy,
    )


def starts_and_ends(result):
    return [(s.strftime("%H:%M"), e.strftime("%H:%M")) for s, e in result]


def test_empty_day_gives_the_first_three_slots():
    assert starts_and_ends(slots()) == [
        ("09:30", "10:00"),
        ("09:45", "10:15"),
        ("10:00", "10:30"),
    ]


def test_non_workday_has_no_slots():
    assert slots(SATURDAY) == []


FOCUS_ROOM = [booked("09:30", "10:00"), booked("10:00", "11:30")]


def test_slots_start_after_the_room_is_free():
    result = slots(minutes=60, room_bookings=FOCUS_ROOM)
    assert starts_and_ends(result) == [
        ("11:45", "12:45"),
        ("12:00", "13:00"),
        ("14:00", "15:00"),
    ]


def test_attendee_calendar_changes_the_answer():
    result = slots(
        minutes=60,
        room_bookings=FOCUS_ROOM,
        people_bookings=[booked("11:45", "12:00")],
    )
    assert starts_and_ends(result) == [
        ("12:00", "13:00"),
        ("14:00", "15:00"),
        ("14:15", "15:15"),
    ]


def test_long_meeting_must_avoid_lunch():
    assert starts_and_ends(slots(minutes=240)) == [
        ("14:00", "18:00"),
        ("14:15", "18:15"),
        ("14:30", "18:30"),
    ]


def test_suggestion_limit_is_honoured():
    assert len(slots(policy=Policy(suggestion_limit=5))) == 5


def test_intern_gets_nothing_for_the_board_room():
    assert slots(room="Board Room", role=Role.INTERN) == []


def existing_bookings(day):
    day_start = datetime.combine(day, DEFAULT_POLICY.work_start)
    day_end = datetime.combine(day, DEFAULT_POLICY.work_end)

    def build(offset_minutes, duration_minutes):
        start = day_start + offset_minutes * MINUTE
        end = start + duration_minutes * MINUTE
        return Booked(start, end, room_free_at(start, end))

    return st.builds(
        build,
        st.integers(0, (day_end - day_start) // MINUTE - 1),
        st.sampled_from(DURATIONS),
    )


@settings(max_examples=150, deadline=None)
@given(
    day=st.sampled_from(WEEKDAYS),
    minutes=st.sampled_from(DURATIONS),
    room=st.sampled_from(ROOMS),
    role=st.sampled_from(Role),
    data=st.data(),
)
def test_find_slots_returns_exactly_the_first_valid_slots(day, minutes, room, role, data):
    bookings = st.lists(existing_bookings(day), max_size=6)
    kwargs = dict(
        room_name=room,
        requester_role=role,
        room_bookings=data.draw(bookings),
        people_bookings=data.draw(bookings),
    )

    result = find_slots(day, minutes, **kwargs)

    assert len(result) <= DEFAULT_POLICY.suggestion_limit
    assert [s for s, _ in result] == sorted({s for s, _ in result})
    for start, end in result:
        assert slot_violations(start, end, **kwargs) == []

    step = timedelta(minutes=DEFAULT_POLICY.slot_step_minutes)
    first = datetime.combine(day, DEFAULT_POLICY.work_start)
    last = datetime.combine(day, DEFAULT_POLICY.work_end)
    every_start = (first + i * step for i in range((last - first) // step + 1))
    valid = [
        (s, s + minutes * MINUTE)
        for s in every_start
        if slot_violations(s, s + minutes * MINUTE, **kwargs) == []
    ]
    assert result == valid[: DEFAULT_POLICY.suggestion_limit]
