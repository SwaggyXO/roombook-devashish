from datetime import date, datetime, time, timedelta

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from .models import Booking, booking_attendees


def _day_bounds(day: date) -> tuple[datetime, datetime]:
    day_start = datetime.combine(day, time.min)
    return day_start, day_start + timedelta(days=1)


def room_bookings(db: Session, room_id: int, day: date) -> list[Booking]:
    day_start, day_end = _day_bounds(day)
    query = select(Booking).where(
        Booking.room_id == room_id,
        Booking.start < day_end,
        Booking.room_free_at > day_start,
    )
    return list(db.scalars(query))


def people_bookings(db: Session, user_ids: set[int], day: date) -> list[Booking]:
    day_start, day_end = _day_bounds(day)
    attended = select(booking_attendees.c.booking_id).where(
        booking_attendees.c.user_id.in_(user_ids)
    )
    query = select(Booking).where(
        Booking.start < day_end,
        Booking.end > day_start,
        or_(Booking.creator_id.in_(user_ids), Booking.id.in_(attended)),
    )
    return list(db.scalars(query))
