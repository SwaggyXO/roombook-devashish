from datetime import datetime

import pytest
from sqlalchemy import select

from app.models import Booking, Room, User
from app.roles import Role
from app.rules import DEFAULT_POLICY, room_free_at
from app.routers.bookings import STATUS_PRIORITY, rejections
from app.scheduling import Violation, slot_violations


def test_list_bookings_for_date(client):
    res = client.get("/bookings", params={"date": "2026-12-07"})
    assert res.status_code == 200
    bookings = res.json()
    assert len(bookings) == 8
    starts = [b["start"] for b in bookings]
    assert starts == sorted(starts)


def test_list_bookings_for_room(client):
    res = client.get("/bookings", params={"date": "2026-12-07", "room_id": 3})
    assert [b["title"] for b in res.json()] == ["Standup sync", "Retro"]


def test_create_booking(client):
    res = client.post(
        "/bookings",
        json={
            "room_id": 3,
            "creator_id": 2,
            "title": "Pairing",
            "attendee_ids": [2, 6],
            "start": "2026-12-07T15:00:00",
            "end": "2026-12-07T15:30:00",
        },
    )
    assert res.status_code == 201
    body = res.json()
    assert body["room"]["name"] == "Huddle"
    assert {a["name"] for a in body["attendees"]} == {"Ben", "Farah"}


def test_overlapping_booking_is_rejected(client):
    res = client.post(
        "/bookings",
        json={
            "room_id": 1,
            "creator_id": 1,
            "attendee_ids": [1],
            "start": "2026-12-07T10:30:00",
            "end": "2026-12-07T11:00:00",
        },
    )
    assert res.status_code == 409


def test_back_to_back_booking_is_allowed(client):
    # The seeded "Standup sync" uses room 3 from 11:45 to 12:15, so this booking starts right as it ends.
    res = client.post(
        "/bookings",
        json={
            "room_id": 3,
            "creator_id": 1,
            "attendee_ids": [1],
            "start": "2026-12-07T12:15:00",
            "end": "2026-12-07T12:45:00",
        },
    )
    assert res.status_code == 201


def test_end_must_be_after_start(client):
    res = client.post(
        "/bookings",
        json={
            "room_id": 1,
            "creator_id": 1,
            "start": "2026-12-07T11:00:00",
            "end": "2026-12-07T10:00:00",
        },
    )
    assert res.status_code == 422


def test_unknown_room(client):
    res = client.post(
        "/bookings",
        json={
            "room_id": 99,
            "creator_id": 1,
            "start": "2026-12-07T10:00:00",
            "end": "2026-12-07T11:00:00",
        },
    )
    assert res.status_code == 404


def test_unknown_attendee(client):
    res = client.post(
        "/bookings",
        json={
            "room_id": 3,
            "creator_id": 1,
            "attendee_ids": [42],
            "start": "2026-12-07T15:00:00",
            "end": "2026-12-07T15:30:00",
        },
    )
    assert res.status_code == 400


def test_seed_stores_room_free_at(db):
    bookings = db.scalars(select(Booking)).all()
    assert bookings
    for b in bookings:
        assert b.room_free_at == room_free_at(b.start, b.end)

    def free_at(title):
        return db.scalars(select(Booking).where(Booking.title == title)).one().room_free_at

    assert free_at("Hiring panel") == datetime(2026, 12, 7, 11, 45)
    assert free_at("Standup sync") == datetime(2026, 12, 7, 12, 15)


def test_create_booking_stores_room_free_at(client, db):
    res = client.post(
        "/bookings",
        json={
            "room_id": 3,
            "creator_id": 2,
            "start": "2026-12-07T09:30:00",
            "end": "2026-12-07T10:45:00",
        },
    )
    assert res.status_code == 201
    assert db.get(Booking, res.json()["id"]).room_free_at == datetime(2026, 12, 7, 11, 0)


MONDAY = "2026-12-07"
SATURDAY = "2026-12-05"
WEDNESDAY = "2026-12-09"
FOCUS_ROOM, BOARD_ROOM, HUDDLE = 1, 2, 3
CHEN, BEN, DIVYA, ELI = 3, 2, 4, 5


def book(client, room_id, creator_id, start, end, *, day=MONDAY, attendee_ids=()):
    return client.post(
        "/bookings",
        json={
            "room_id": room_id,
            "creator_id": creator_id,
            "attendee_ids": list(attendee_ids),
            "start": f"{day}T{start}:00",
            "end": f"{day}T{end}:00",
        },
    )


def test_seed_bookings_satisfy_every_rule(db):
    bookings = db.scalars(select(Booking)).all()
    assert bookings
    for b in bookings:
        others = [o for o in bookings if o.id != b.id]
        people = {b.creator_id, *(a.id for a in b.attendees)}
        violations = slot_violations(
            b.start,
            b.end,
            room_name=b.room.name,
            requester_role=b.creator.role,
            room_bookings=[o for o in others if o.room_id == b.room_id],
            people_bookings=[
                o for o in others if people & {o.creator_id, *(a.id for a in o.attendees)}
            ],
        )
        assert violations == [], b.title


@pytest.mark.parametrize(
    "room, day, start, end, reason",
    [
        (HUDDLE, SATURDAY, "10:00", "11:00", "working days"),
        (HUDDLE, MONDAY, "09:15", "09:45", "bookings must fall within"),
        (FOCUS_ROOM, MONDAY, "18:00", "18:45", "bookings must fall within"),
        (HUDDLE, MONDAY, "12:30", "13:30", "cannot overlap lunch"),
        (FOCUS_ROOM, WEDNESDAY, "14:15", "18:30", "duration must be between"),
    ],
)
def test_booking_that_breaks_a_rule_is_rejected_with_the_reason(client, room, day, start, end, reason):
    res = book(client, room, ELI, start, end, day=day)
    assert res.status_code == 422
    assert reason in res.json()["detail"]


def test_broken_rule_beats_a_room_clash(client):
    assert book(client, HUDDLE, ELI, "12:00", "12:30").status_code == 409

    res = book(client, HUDDLE, ELI, "12:00", "13:30")

    assert res.status_code == 422
    assert "cannot overlap lunch" in res.json()["detail"]
    assert "already booked" not in res.json()["detail"]


def test_restricted_room_beats_a_broken_rule(client):
    res = book(client, BOARD_ROOM, DIVYA, "10:00", "11:00", day=SATURDAY)

    assert res.status_code == 403
    assert res.json()["detail"] == "Divya (intern) can't book the Board Room"


def test_every_violation_has_a_response():
    responses = rejections(User(name="Divya", role=Role.INTERN), Room(name="Board Room"), 20)
    assert set(responses) == set(Violation)
    for status, message in responses.values():
        assert status in STATUS_PRIORITY
        assert message


def test_short_meeting_may_overlap_lunch(client):
    assert book(client, HUDDLE, ELI, "13:00", "13:30").status_code == 201


def test_room_stays_busy_during_the_previous_meetings_cleaning(client):
    res = book(client, FOCUS_ROOM, ELI, "11:30", "12:00")
    assert res.status_code == 409
    assert res.json()["detail"] == "Room is already booked for that time"


def test_attendee_busy_in_another_room_is_rejected(client):
    res = book(client, FOCUS_ROOM, ELI, "12:00", "12:30", attendee_ids=[BEN])
    assert res.status_code == 409
    assert res.json()["detail"] == "An attendee is already booked at that time"


def test_creator_busy_in_another_room_is_rejected(client):
    res = book(client, FOCUS_ROOM, BEN, "12:00", "12:30")
    assert res.status_code == 409
    assert res.json()["detail"] == "An attendee is already booked at that time"


def test_intern_cannot_book_the_board_room(client):
    res = book(client, BOARD_ROOM, DIVYA, "10:00", "11:00")
    assert res.status_code == 403
    assert res.json()["detail"] == "Divya (intern) can't book the Board Room"


def test_intern_may_attend_a_board_room_booking_made_by_someone_else(client):
    res = book(client, BOARD_ROOM, CHEN, "14:00", "14:30", attendee_ids=[DIVYA])
    assert res.status_code == 201


@pytest.mark.parametrize("attendee_ids", [[], [ELI]])
def test_creator_is_always_an_attendee_once(client, attendee_ids):
    res = book(client, FOCUS_ROOM, ELI, "12:00", "12:30", attendee_ids=attendee_ids)
    assert res.status_code == 201
    assert [a["id"] for a in res.json()["attendees"]] == [ELI]


@pytest.mark.parametrize("attendee_ids", [[], [BEN]])
@pytest.mark.parametrize("index", range(DEFAULT_POLICY.suggestion_limit))
def test_every_suggested_slot_can_be_booked_and_then_disappears(client, index, attendee_ids):
    request = {
        "requester_id": ELI,
        "attendee_ids": attendee_ids,
        "duration_minutes": 60,
        "date": MONDAY,
    }
    suggested = client.post(f"/rooms/{FOCUS_ROOM}/suggest", json=request).json()["slots"]
    slot = suggested[index]

    res = client.post(
        "/bookings",
        json={
            "room_id": FOCUS_ROOM,
            "creator_id": ELI,
            "attendee_ids": attendee_ids,
            "start": slot["start"],
            "end": slot["end"],
        },
    )

    assert res.status_code == 201
    after = client.post(f"/rooms/{FOCUS_ROOM}/suggest", json=request).json()["slots"]
    assert slot not in after
