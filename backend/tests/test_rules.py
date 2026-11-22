from dataclasses import FrozenInstanceError
from datetime import time

import pytest

from app.roles import Role
from app.rules import DEFAULT_POLICY, Policy


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
