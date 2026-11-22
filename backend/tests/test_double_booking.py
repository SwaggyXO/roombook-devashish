import os
import threading
from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.db import Base, get_db
from app.main import app
from app.messages import ROOM_ALREADY_BOOKED
from app.models import Booking, create_schema
from app.rules import room_free_at
from app.seed import seed

WAIT_TIMEOUT_SECONDS = 10

ASHA = 1
FARAH = 6
HUDDLE = 3
# The seed has no Huddle booking on this morning, and neither Asha nor Farah has a meeting that day.
FREE_DAY = "2026-12-08"


POSTGRES_URL = os.getenv("TEST_POSTGRES_URL")
BACKENDS = [
    "sqlite",
    pytest.param(
        "postgres",
        marks=pytest.mark.skipif(
            not POSTGRES_URL, reason="set TEST_POSTGRES_URL to also run against Postgres"
        ),
    ),
]


@pytest.fixture(params=BACKENDS)
def engine(request, tmp_path):
    if request.param == "sqlite":
        engine = create_engine(
            f"sqlite:///{tmp_path / 'race.db'}",
            connect_args={"check_same_thread": False, "timeout": 30},
        )
    else:
        engine = create_engine(POSTGRES_URL)
        Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield engine
    engine.dispose()


@pytest.fixture
def overlap_error(engine):
    if engine.dialect.name == "sqlite":
        return ROOM_ALREADY_BOOKED
    return "bookings_no_room_overlap"


@pytest.fixture
def file_session_factory(engine):
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with factory() as db:
        seed(db)
    return factory


@pytest.fixture
def guarded_db(file_session_factory):
    with file_session_factory() as session:
        yield session


@pytest.fixture
def file_client(file_session_factory):
    def override_get_db():
        db = file_session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_simultaneous_overlapping_bookings_allow_exactly_one(file_client, file_session_factory):
    both_ready_to_insert = threading.Barrier(2, timeout=WAIT_TIMEOUT_SECONDS)
    arrivals = []

    @event.listens_for(file_session_factory, "before_flush")
    def wait_for_other_request_before_insert(session, flush_context, instances):
        thread_id = threading.get_ident()
        if thread_id not in arrivals:
            arrivals.append(thread_id)
            both_ready_to_insert.wait()

    requests = [
        {"creator_id": ASHA, "start": f"{FREE_DAY}T10:00:00", "end": f"{FREE_DAY}T10:30:00"},
        {"creator_id": FARAH, "start": f"{FREE_DAY}T10:15:00", "end": f"{FREE_DAY}T10:45:00"},
    ]
    responses = [None, None]
    errors = []

    def book(index):
        try:
            responses[index] = file_client.post(
                "/bookings",
                json={
                    "room_id": HUDDLE,
                    "title": f"Race {index}",
                    "attendee_ids": [requests[index]["creator_id"]],
                    **requests[index],
                },
            )
        except Exception as error:
            errors.append(error)

    threads = [threading.Thread(target=book, args=(i,)) for i in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=2 * WAIT_TIMEOUT_SECONDS)

    assert not any(thread.is_alive() for thread in threads)
    assert errors == []
    assert len(arrivals) == 2
    assert sorted(r.status_code for r in responses) == [201, 409]
    loser = next(r for r in responses if r.status_code == 409)
    assert loser.json()["detail"] == ROOM_ALREADY_BOOKED
    with file_session_factory() as db:
        racing = db.scalars(select(Booking).where(Booking.title.like("Race %"))).all()
    assert len(racing) == 1


FOCUS_ROOM = 1
BOARD_ROOM = 2
DAY = "2026-12-07"


def make_booking(room_id, start_time, end_time, day=DAY):
    start = datetime.fromisoformat(f"{day}T{start_time}")
    end = datetime.fromisoformat(f"{day}T{end_time}")
    return Booking(
        room_id=room_id,
        creator_id=ASHA,
        title="Direct insert",
        start=start,
        end=end,
        room_free_at=room_free_at(start, end),
    )


def test_database_rejects_overlapping_booking_in_same_room(guarded_db, overlap_error):
    guarded_db.add(make_booking(FOCUS_ROOM, "10:30", "11:00"))
    with pytest.raises(IntegrityError, match=overlap_error):
        guarded_db.commit()


def test_database_rejects_booking_inside_cleaning_window(guarded_db, overlap_error):
    # The Hiring panel (10:00-11:30, Focus Room) keeps the room busy until 11:45.
    guarded_db.add(make_booking(FOCUS_ROOM, "11:30", "12:00"))
    with pytest.raises(IntegrityError, match=overlap_error):
        guarded_db.commit()


def direct_inserts(guarded_db):
    return guarded_db.scalar(select(func.count()).select_from(Booking).where(Booking.title == "Direct insert"))


def test_database_rejects_booking_whose_own_cleaning_overlaps_next_meeting(guarded_db, overlap_error):
    # 13:45-15:00 is over 60 minutes, so the room stays busy until 15:15, past the 15:00 Quarterly review.
    guarded_db.add(make_booking(BOARD_ROOM, "13:45", "15:00"))
    with pytest.raises(IntegrityError, match=overlap_error):
        guarded_db.commit()


def test_database_allows_booking_ending_exactly_when_next_meeting_starts(guarded_db):
    guarded_db.add(make_booking(BOARD_ROOM, "14:30", "15:00"))
    guarded_db.commit()
    assert direct_inserts(guarded_db) == 1


def test_database_allows_booking_starting_when_room_is_free_again(guarded_db):
    guarded_db.add(make_booking(FOCUS_ROOM, "11:45", "12:15"))
    guarded_db.commit()
    assert direct_inserts(guarded_db) == 1


def test_database_allows_same_time_in_different_room(guarded_db):
    guarded_db.add(make_booking(BOARD_ROOM, "10:00", "11:30", day="2026-12-08"))
    guarded_db.add(make_booking(HUDDLE, "10:00", "11:30", day="2026-12-08"))
    guarded_db.commit()
    assert direct_inserts(guarded_db) == 2


def test_database_rejects_update_that_moves_booking_into_overlap(guarded_db, overlap_error):
    booking = make_booking(FOCUS_ROOM, "12:00", "12:30")
    guarded_db.add(booking)
    guarded_db.commit()
    moved = make_booking(FOCUS_ROOM, "10:30", "11:00")
    booking.start, booking.end, booking.room_free_at = moved.start, moved.end, moved.room_free_at
    with pytest.raises(IntegrityError, match=overlap_error):
        guarded_db.commit()


def test_database_allows_update_that_overlaps_only_the_bookings_own_old_time(guarded_db):
    booking = make_booking(FOCUS_ROOM, "12:00", "12:30")
    guarded_db.add(booking)
    guarded_db.commit()
    moved = make_booking(FOCUS_ROOM, "12:15", "12:45")
    booking.start, booking.end, booking.room_free_at = moved.start, moved.end, moved.room_free_at
    guarded_db.commit()
    assert guarded_db.scalar(select(Booking.start).where(Booking.id == booking.id)) == moved.start


def test_startup_adds_guards_to_a_database_created_without_them(
    engine, file_session_factory, overlap_error
):
    with engine.begin() as connection:
        if engine.dialect.name == "sqlite":
            connection.execute(text("DROP TRIGGER bookings_no_room_overlap_insert"))
            connection.execute(text("DROP TRIGGER bookings_no_room_overlap_update"))
        else:
            connection.execute(text("ALTER TABLE bookings DROP CONSTRAINT bookings_no_room_overlap"))

    create_schema(engine)

    with file_session_factory() as session:
        session.add(make_booking(FOCUS_ROOM, "10:30", "11:00"))
        with pytest.raises(IntegrityError, match=overlap_error):
            session.commit()


def test_integrity_error_unrelated_to_room_clash_is_not_reported_as_409(
    engine, file_client, file_session_factory
):
    with engine.begin() as connection:
        if engine.dialect.name == "sqlite":
            connection.execute(
                text(
                    """
                    CREATE TRIGGER test_only_unrelated_constraint BEFORE INSERT ON bookings
                    WHEN NEW.title = 'Unrelated failure'
                    BEGIN
                        SELECT RAISE(ABORT, 'test_only_unrelated_constraint');
                    END
                    """
                )
            )
        else:
            connection.execute(
                text(
                    "ALTER TABLE bookings ADD CONSTRAINT test_only_unrelated_constraint "
                    "CHECK (title <> 'Unrelated failure')"
                )
            )

    with pytest.raises(IntegrityError, match="test_only_unrelated_constraint"):
        file_client.post(
            "/bookings",
            json={
                "room_id": HUDDLE,
                "creator_id": ASHA,
                "title": "Unrelated failure",
                "attendee_ids": [ASHA],
                "start": f"{FREE_DAY}T10:00:00",
                "end": f"{FREE_DAY}T10:30:00",
            },
        )


@pytest.fixture
def deadlock_once_on_insert(engine):
    drop_statements = (
        "DROP TRIGGER IF EXISTS test_only_deadlock_once ON bookings",
        "DROP FUNCTION IF EXISTS test_only_raise_deadlock_once()",
        "DROP SEQUENCE IF EXISTS test_only_deadlock_once_calls",
    )
    with engine.begin() as connection:
        for statement in drop_statements:
            connection.execute(text(statement))
        connection.execute(text("CREATE SEQUENCE test_only_deadlock_once_calls"))
        connection.execute(
            text(
                """
                CREATE FUNCTION test_only_raise_deadlock_once() RETURNS trigger AS $$
                BEGIN
                    IF nextval('test_only_deadlock_once_calls') = 1 THEN
                        RAISE EXCEPTION 'simulated deadlock' USING ERRCODE = '40P01';
                    END IF;
                    RETURN NEW;
                END
                $$ LANGUAGE plpgsql
                """
            )
        )
        connection.execute(
            text(
                """
                CREATE TRIGGER test_only_deadlock_once BEFORE INSERT ON bookings
                FOR EACH ROW EXECUTE FUNCTION test_only_raise_deadlock_once()
                """
            )
        )
    yield
    with engine.begin() as connection:
        for statement in drop_statements:
            connection.execute(text(statement))


@pytest.mark.parametrize("engine", [BACKENDS[1]], indirect=True)
def test_booking_is_retried_after_postgres_reports_a_deadlock(
    file_client, deadlock_once_on_insert
):
    res = file_client.post(
        "/bookings",
        json={
            "room_id": HUDDLE,
            "creator_id": ASHA,
            "title": "Retried",
            "attendee_ids": [ASHA],
            "start": f"{FREE_DAY}T10:00:00",
            "end": f"{FREE_DAY}T10:30:00",
        },
    )
    assert res.status_code == 201
