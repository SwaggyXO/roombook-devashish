import pytest

MONDAY = "2026-12-07"
SATURDAY = "2026-12-05"


def suggest(
    client, room_id, *, requester_id, duration_minutes=60, attendee_ids=(), date=MONDAY, after=None
):
    body = {
        "requester_id": requester_id,
        "attendee_ids": list(attendee_ids),
        "duration_minutes": duration_minutes,
        "date": date,
    }
    if after is not None:
        body["after"] = after
    return client.post(f"/rooms/{room_id}/suggest", json=body)


def slot(start, end):
    return {
        "start": f"{MONDAY}T{start}:00+05:30",
        "end": f"{MONDAY}T{end}:00+05:30",
    }


def test_spec_example_for_the_huddle(client):
    res = suggest(client, 3, requester_id=3, attendee_ids=[1, 2], duration_minutes=45)
    assert res.status_code == 200
    assert res.json() == {
        "slots": [slot("12:15", "13:00"), slot("14:00", "14:45"), slot("14:15", "15:00")]
    }


def test_focus_room_waits_for_the_hiring_panels_cleaning(client):
    res = suggest(client, 1, requester_id=5)
    assert res.json() == {
        "slots": [slot("11:45", "12:45"), slot("12:00", "13:00"), slot("14:30", "15:30")]
    }


def test_attendee_booked_in_another_room_removes_slots(client):
    res = suggest(client, 1, requester_id=5, attendee_ids=[2])
    assert res.json() == {
        "slots": [slot("14:30", "15:30"), slot("14:45", "15:45"), slot("15:00", "16:00")]
    }


def test_non_workday_has_no_slots(client):
    res = suggest(client, 1, requester_id=5, date=SATURDAY)
    assert res.status_code == 200
    assert res.json() == {"slots": []}


def test_intern_cannot_book_the_board_room(client):
    res = suggest(client, 2, requester_id=4)
    assert res.status_code == 403
    assert res.json()["detail"] == "Divya (intern) can't book the Board Room"


def test_manager_can_book_the_board_room(client):
    res = suggest(client, 2, requester_id=3, duration_minutes=30)
    assert res.status_code == 200
    assert res.json() == {
        "slots": [slot("13:15", "13:45"), slot("13:30", "14:00"), slot("13:45", "14:15")]
    }


@pytest.mark.parametrize("duration", [50, 0, 255])
def test_invalid_duration_is_rejected(client, duration):
    assert suggest(client, 1, requester_id=5, duration_minutes=duration).status_code == 422


def test_unknown_room(client):
    assert suggest(client, 42, requester_id=5).status_code == 404


def test_unknown_requester(client):
    assert suggest(client, 1, requester_id=42).status_code == 404


def test_unknown_attendee(client):
    assert suggest(client, 1, requester_id=5, attendee_ids=[42]).status_code == 400


def test_booking_made_by_a_non_attendee_creator_blocks_that_person(client):
    created = client.post(
        "/bookings",
        json={
            "room_id": 3,
            "creator_id": 5,
            "attendee_ids": [],
            "start": f"{MONDAY}T14:30:00",
            "end": f"{MONDAY}T15:30:00",
        },
    )
    assert created.status_code == 201
    res = suggest(client, 1, requester_id=5)
    assert res.json() == {
        "slots": [slot("11:45", "12:45"), slot("12:00", "13:00"), slot("16:30", "17:30")]
    }


def test_booking_where_the_person_is_only_an_attendee_blocks_them(client):
    res = suggest(client, 1, requester_id=5, attendee_ids=[3])
    assert res.json() == {
        "slots": [slot("11:45", "12:45"), slot("12:00", "13:00"), slot("17:00", "18:00")]
    }


def test_after_returns_the_next_slots(client):
    # Focus Room, Eli, 60 minutes: the first page is 11:45, 12:00, 14:30.
    # 12:15 hits lunch and Eli's vendor call is 14:00-14:30, so 12:00, 14:30 and 14:45 follow.
    res = suggest(client, 1, requester_id=5, after=f"{MONDAY}T11:45:00+05:30")
    assert res.json() == {
        "slots": [slot("12:00", "13:00"), slot("14:30", "15:30"), slot("14:45", "15:45")]
    }


def test_after_the_second_slot_of_the_spec_example(client):
    # After 14:00, only 14:15 fits before the Quarterly review takes Asha and Chen at 15:00.
    res = suggest(
        client, 3, requester_id=3, attendee_ids=[1, 2], duration_minutes=45,
        after=f"{MONDAY}T14:00:00+05:30",
    )
    assert res.json() == {"slots": [slot("14:15", "15:00")]}


def test_after_the_third_slot_of_the_spec_example_has_nothing_left(client):
    # Asha and Chen are in the Quarterly review until 17:00, and Asha's Retro starts at 17:30.
    res = suggest(
        client, 3, requester_id=3, attendee_ids=[1, 2], duration_minutes=45,
        after=f"{MONDAY}T14:15:00+05:30",
    )
    assert res.json() == {"slots": []}


def test_after_the_end_of_the_day_has_no_slots(client):
    res = suggest(client, 1, requester_id=5, after=f"{MONDAY}T18:30:00+05:30")
    assert res.json() == {"slots": []}


def test_after_accepts_a_time_in_another_zone(client):
    res = suggest(client, 1, requester_id=5, after=f"{MONDAY}T06:15:00+00:00")
    assert res.json() == {
        "slots": [slot("12:00", "13:00"), slot("14:30", "15:30"), slot("14:45", "15:45")]
    }


def test_after_must_be_on_the_grid(client):
    assert suggest(client, 1, requester_id=5, after=f"{MONDAY}T11:50:00+05:30").status_code == 422
