from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, String, Table, event, text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.orm import Mapped, mapped_column, relationship

from . import messages
from .db import Base
from .roles import Role

booking_attendees = Table(
    "booking_attendees",
    Base.metadata,
    Column("booking_id", ForeignKey("bookings.id", ondelete="CASCADE"), primary_key=True),
    Column("user_id", ForeignKey("users.id"), primary_key=True),
)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    role: Mapped[Role] = mapped_column(
        SAEnum(
            Role,
            native_enum=False,
            values_callable=lambda roles: [r.value for r in roles],
            length=20,
            validate_strings=True,
            create_constraint=True,
        ),
        default=Role.EMPLOYEE,
    )


class Room(Base):
    __tablename__ = "rooms"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    capacity: Mapped[int]


class Booking(Base):
    __tablename__ = "bookings"

    id: Mapped[int] = mapped_column(primary_key=True)
    room_id: Mapped[int] = mapped_column(ForeignKey("rooms.id"), index=True)
    creator_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    title: Mapped[str] = mapped_column(String(200), default="")
    start: Mapped[datetime] = mapped_column(DateTime, index=True)
    end: Mapped[datetime] = mapped_column(DateTime)
    room_free_at: Mapped[datetime] = mapped_column(DateTime)

    room: Mapped[Room] = relationship()
    creator: Mapped[User] = relationship()
    attendees: Mapped[list[User]] = relationship(secondary=booking_attendees)


_BOOKING_GUARDS = (
    ("bookings_no_room_overlap_insert", "INSERT", ""),
    ("bookings_no_room_overlap_update", "UPDATE OF room_id, start, room_free_at", "AND id != NEW.id"),
)

_TRIGGER = """
CREATE TRIGGER IF NOT EXISTS {name} BEFORE {trigger_event} ON bookings FOR EACH ROW
BEGIN
    SELECT RAISE(ABORT, '{message}')
    WHERE EXISTS (
        SELECT 1 FROM bookings
        WHERE room_id = NEW.room_id
          AND start < NEW.room_free_at
          AND NEW.start < room_free_at
          {other_rows_only}
    );
END
"""


def install_booking_guards(connection: Connection) -> None:
    """SQLite has no exclusion constraints, so triggers refuse overlapping room windows instead."""
    for name, trigger_event, other_rows_only in _BOOKING_GUARDS:
        connection.execute(
            text(
                _TRIGGER.format(
                    name=name,
                    trigger_event=trigger_event,
                    message=messages.ROOM_ALREADY_BOOKED,
                    other_rows_only=other_rows_only,
                )
            )
        )


@event.listens_for(Booking.__table__, "after_create")
def _install_guards_on_create(target, connection, **kwargs):
    if connection.dialect.name == "sqlite":
        install_booking_guards(connection)


def create_schema(engine: Engine) -> None:
    """Create missing tables, and add the guards to databases created before they existed."""
    Base.metadata.create_all(bind=engine)
    if engine.dialect.name == "sqlite":
        with engine.begin() as connection:
            install_booking_guards(connection)
