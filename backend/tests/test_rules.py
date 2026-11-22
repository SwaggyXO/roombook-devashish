from dataclasses import FrozenInstanceError
from datetime import datetime, time, timedelta

import pytest

from app.roles import Role
from app.rules import DEFAULT_POLICY, Policy, room_free_at


def test_default_policy_matches_spec():
    p = DEFAULT_POLICY
    assert (p.work_start, p.work_end) == (time(9, 30), time(18, 30))
    assert p.workdays == {0, 1, 2, 3, 4}
    assert (p.lunch_start, p.lunch_end) == (time(13, 0), time(14, 0))
    assert p.lunch_exempt_max_minutes == 30
    assert (p.buffer_minutes, p.buffer_threshold_minutes) == (15, 60)
    assert (p.slot_step_minutes, p.duration_step_minutes) == (15, 15)
    assert (p.min_duration_minutes, p.max_duration_minutes) == (15, 240)
    assert p.restricted == {("Board Room", Role.INTERN)}
    assert p.suggestion_limit == 3


def test_policy_is_data_and_immutable():
    custom = Policy(lunch_start=time(12), lunch_end=time(13))
    assert custom.lunch_start == time(12)
    assert DEFAULT_POLICY.lunch_start == time(13)
    with pytest.raises(FrozenInstanceError):
        DEFAULT_POLICY.buffer_minutes = 0
    hash(DEFAULT_POLICY)


@pytest.mark.parametrize(
    "bad",
    [
        {"slot_step_minutes": 0},
        {"duration_step_minutes": -15},
        {"work_start": time(18, 30), "work_end": time(9, 30)},
        {"work_start": time(9), "work_end": time(9)},
    ],
)
def test_policy_rejects_invalid_values(bad):
    with pytest.raises(ValueError):
        Policy(**bad)


@pytest.mark.parametrize(
    "minutes, buffer",
    [(30, 0), (60, 0), (75, 15), (240, 15)],
)
def test_room_free_at_adds_buffer_only_above_threshold(minutes, buffer):
    start = datetime(2026, 12, 7, 10, 0)
    end = start + timedelta(minutes=minutes)
    assert room_free_at(start, end) == end + timedelta(minutes=buffer)


def test_room_free_at_uses_custom_policy():
    start = datetime(2026, 12, 7, 10, 0)
    end = datetime(2026, 12, 7, 11, 30)
    assert room_free_at(start, end, Policy(buffer_minutes=10)) == datetime(2026, 12, 7, 11, 40)
