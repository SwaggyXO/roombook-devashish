from collections.abc import Callable
from datetime import date, datetime, time, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session, selectinload

from .. import messages
from ..availability import people_bookings, room_bookings
from ..db import get_db
from ..models import Booking, Room, User
from ..rules import DEFAULT_POLICY, duration_error, room_free_at
from ..scheduling import Violation, overlaps, slot_violations
from ..schemas import BookingIn, BookingOut

router = APIRouter(prefix="/bookings", tags=["bookings"])


@router.get("", response_model=list[BookingOut])
def list_bookings(
    date: date | None = None,
    room_id: int | None = None,
    db: Session = Depends(get_db),
):
    query = (
        select(Booking)
        .options(selectinload(Booking.attendees), selectinload(Booking.room))
        .order_by(Booking.start)
    )
    if date is not None:
        day_start = datetime.combine(date, time.min)
        query = query.where(Booking.start >= day_start, Booking.start < day_start + timedelta(days=1))
    if room_id is not None:
        query = query.where(Booking.room_id == room_id)
    return db.scalars(query).all()


STATUS_PRIORITY = (403, 422, 409)


def rejections(
    creator: User, room: Room, duration_minutes: float
) -> dict[Violation, tuple[int, str | None]]:
    """The (status, message) the API answers with for each rule a booking can break.

    The DURATION message is only set when duration_minutes is actually invalid.
    """
    policy = DEFAULT_POLICY
    return {
        Violation.RESTRICTED_ROOM: (403, messages.restricted_room(creator.name, creator.role, room.name)),
        Violation.DURATION: (422, duration_error(duration_minutes)),
        Violation.OFF_GRID: (422, f"start must be on a {policy.slot_step_minutes}-minute boundary"),
        Violation.NON_WORKDAY: (422, "bookings are only allowed on working days"),
        Violation.OUTSIDE_HOURS: (
            422,
            f"bookings must fall within {policy.work_start:%H:%M}-{policy.work_end:%H:%M}",
        ),
        Violation.LUNCH: (
            422,
            f"meetings over {policy.lunch_exempt_max_minutes} minutes cannot overlap lunch "
            f"({policy.lunch_start:%H:%M}-{policy.lunch_end:%H:%M})",
        ),
        Violation.ROOM_BUSY: (409, messages.ROOM_ALREADY_BOOKED),
        Violation.ATTENDEE_BUSY: (409, messages.ATTENDEE_ALREADY_BOOKED),
    }


DEADLOCK_RETRIES = 2
POSTGRES_DEADLOCK_DETECTED = "40P01"


def commit_booking(db: Session, make_booking: Callable[[], Booking]) -> Booking:
    """Insert a new booking, trying again if Postgres picks this request as a deadlock victim.

    Two simultaneous clashing inserts can wait on each other's exclusion check. Postgres ends one
    of them with a deadlock error, and the retry then fails the normal way, as a room clash.
    """
    for attempt in range(DEADLOCK_RETRIES + 1):
        booking = make_booking()
        db.add(booking)
        try:
            db.commit()
            return booking
        except OperationalError as error:
            db.rollback()
            is_deadlock = getattr(error.orig, "sqlstate", None) == POSTGRES_DEADLOCK_DETECTED
            if not is_deadlock or attempt == DEADLOCK_RETRIES:
                raise


@router.post("", response_model=BookingOut, status_code=201)
def create_booking(payload: BookingIn, db: Session = Depends(get_db)):
    room = db.get(Room, payload.room_id)
    if room is None:
        raise HTTPException(status_code=404, detail="Room not found")
    creator = db.get(User, payload.creator_id)
    if creator is None:
        raise HTTPException(status_code=404, detail="Creator not found")

    attendee_ids = set(payload.attendee_ids)
    attendees = db.scalars(select(User).where(User.id.in_(attendee_ids))).all()
    if len(attendees) != len(attendee_ids):
        raise HTTPException(status_code=400, detail="Unknown attendee")
    if creator.id not in attendee_ids:
        attendees = [*attendees, creator]

    violations = slot_violations(
        payload.start,
        payload.end,
        room_name=room.name,
        requester_role=creator.role,
        room_bookings=room_bookings(db, room.id, payload.start.date()),
        people_bookings=people_bookings(db, attendee_ids | {creator.id}, payload.start.date()),
    )
    if violations:
        duration_minutes = (payload.end - payload.start) / timedelta(minutes=1)
        responses = [rejections(creator, room, duration_minutes)[v] for v in violations]
        for status in STATUS_PRIORITY:
            details = [message for code, message in responses if code == status]
            if details:
                raise HTTPException(status_code=status, detail="; ".join(details))

    free_at = room_free_at(payload.start, payload.end)

    def make_booking() -> Booking:
        return Booking(
            room_id=room.id,
            creator_id=creator.id,
            title=payload.title,
            start=payload.start,
            end=payload.end,
            room_free_at=free_at,
            attendees=list(attendees),
        )

    try:
        booking = commit_booking(db, make_booking)
    except IntegrityError:
        db.rollback()
        room_is_taken = any(
            overlaps(payload.start, free_at, other.start, other.room_free_at)
            for other in room_bookings(db, room.id, payload.start.date())
        )
        if not room_is_taken:
            raise
        raise HTTPException(status_code=409, detail=messages.ROOM_ALREADY_BOOKED)
    db.refresh(booking)
    return booking
