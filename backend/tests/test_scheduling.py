from datetime import datetime

import pytest

from app.scheduling import overlaps


def t(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 12, 7, hour, minute)


@pytest.mark.parametrize(
    "a, b, expected",
    [
        ((t(10), t(11)), (t(11), t(12)), False),
        ((t(11), t(12)), (t(10), t(11)), False),
        ((t(9), t(12)), (t(10), t(11)), True),
        ((t(10), t(11)), (t(10), t(11)), True),
        ((t(9), t(10)), (t(11), t(12)), False),
        ((t(10), t(11)), (t(10, 30), t(11, 30)), True),
    ],
    ids=["touching-after", "touching-before", "nested", "identical", "disjoint", "partial"],
)
def test_overlaps(a, b, expected):
    assert overlaps(*a, *b) is expected
