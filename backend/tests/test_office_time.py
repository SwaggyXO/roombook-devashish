from datetime import datetime, timezone

import pytest

from app.office_time import to_iso_ist, to_office_time


def book(client, start, end, **extra):
    return client.post(
        "/bookings",
        json={"room_id": 1, "creator_id": 1, "start": start, "end": end, **extra},
    )


def test_utc_input_is_converted_to_ist(client):
    res = book(client, "2026-12-07T06:45:00Z", "2026-12-07T07:15:00Z")
    assert res.status_code == 201
    assert res.json()["start"] == "2026-12-07T12:15:00+05:30"
    assert res.json()["end"] == "2026-12-07T12:45:00+05:30"


def test_ist_offset_input_is_unchanged(client):
    res = book(client, "2026-12-07T12:15:00+05:30", "2026-12-07T12:45:00+05:30")
    assert res.status_code == 201
    assert res.json()["start"] == "2026-12-07T12:15:00+05:30"


def test_negative_offset_input_is_converted(client):
    res = book(client, "2026-12-07T01:45:00-05:00", "2026-12-07T02:15:00-05:00")
    assert res.status_code == 201
    assert res.json()["start"] == "2026-12-07T12:15:00+05:30"


def test_naive_input_is_treated_as_ist(client):
    res = book(client, "2026-12-07T12:15:00", "2026-12-07T12:45:00")
    assert res.status_code == 201
    assert res.json()["start"] == "2026-12-07T12:15:00+05:30"


@pytest.mark.parametrize("start", ["2026-12-07T10:07:00", "2026-12-07T10:00:30"])
def test_off_grid_start_is_rejected(client, start):
    assert book(client, start, "2026-12-07T11:00:00").status_code == 422


def test_off_grid_end_is_rejected(client):
    assert book(client, "2026-12-07T12:15:00", "2026-12-07T12:40:00").status_code == 422


def test_out_of_range_time_is_rejected(client):
    res = book(client, "9999-12-31T23:45:00-05:00", "9999-12-31T23:45:00-04:00")
    assert res.status_code == 422


def test_booking_made_in_utc_is_listed_on_its_ist_date(client):
    res = book(client, "2026-12-08T05:30:00Z", "2026-12-08T06:00:00Z")
    assert res.status_code == 201
    listed = client.get("/bookings", params={"date": "2026-12-08"}).json()
    assert res.json()["id"] in [b["id"] for b in listed]


def test_listing_uses_ist_offset(client):
    bookings = client.get("/bookings").json()
    assert bookings
    for b in bookings:
        assert b["start"].endswith("+05:30")
        assert b["end"].endswith("+05:30")


def test_to_office_time_rolls_the_date():
    utc = datetime(2026, 12, 6, 20, 0, tzinfo=timezone.utc)
    assert to_office_time(utc) == datetime(2026, 12, 7, 1, 30)


def test_to_office_time_rejects_overflow():
    with pytest.raises(ValueError, match="out of range"):
        to_office_time(datetime.fromisoformat("9999-12-31T23:45:00-05:00"))


def test_to_iso_ist_converts_aware_and_labels_naive():
    utc = datetime(2026, 12, 7, 4, 30, tzinfo=timezone.utc)
    assert to_iso_ist(utc) == "2026-12-07T10:00:00+05:30"
    assert to_iso_ist(datetime(2026, 12, 7, 10, 0)) == "2026-12-07T10:00:00+05:30"
