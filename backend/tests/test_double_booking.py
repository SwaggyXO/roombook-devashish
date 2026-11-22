import threading

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import sessionmaker

from app.db import Base, get_db
from app.main import app
from app.models import Booking
from app.seed import seed

WAIT_TIMEOUT_SECONDS = 10

ASHA = 1
FARAH = 6
HUDDLE = 3
# The seed has no Huddle booking on this morning, and neither Asha nor Farah has a meeting that day.
FREE_DAY = "2026-12-08"


@pytest.fixture
def file_session_factory(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'race.db'}",
        connect_args={"check_same_thread": False, "timeout": 30},
    )
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with factory() as db:
        seed(db)
    yield factory
    engine.dispose()


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
        arrivals.append(threading.current_thread().name)
        both_ready_to_insert.wait()

    requests = [
        {"creator_id": ASHA, "start": f"{FREE_DAY}T10:00:00", "end": f"{FREE_DAY}T10:30:00"},
        {"creator_id": FARAH, "start": f"{FREE_DAY}T10:15:00", "end": f"{FREE_DAY}T10:45:00"},
    ]
    statuses = [None, None]
    errors = []

    def book(index):
        try:
            statuses[index] = file_client.post(
                "/bookings",
                json={
                    "room_id": HUDDLE,
                    "title": f"Race {index}",
                    "attendee_ids": [requests[index]["creator_id"]],
                    **requests[index],
                },
            ).status_code
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
    assert sorted(statuses) == [201, 409]
    with file_session_factory() as db:
        racing = db.scalars(select(Booking).where(Booking.title.like("Race %"))).all()
    assert len(racing) == 1
