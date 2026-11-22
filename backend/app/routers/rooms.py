from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import messages
from ..availability import people_bookings, room_bookings
from ..db import get_db
from ..models import Room, User
from ..rules import can_book
from ..scheduling import find_slots
from ..schemas import RoomAccessOut, RoomIn, RoomOut, SlotOut, SuggestIn, SuggestOut

router = APIRouter(prefix="/rooms", tags=["rooms"])


@router.get("", response_model=list[RoomAccessOut], response_model_exclude_none=True)
def list_rooms(user_id: int | None = None, db: Session = Depends(get_db)):
    rooms = db.scalars(select(Room).order_by(Room.id)).all()
    if user_id is None:
        return rooms
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return [
        RoomAccessOut.model_validate(room).model_copy(
            update={"bookable": can_book(user.role, room.name)}
        )
        for room in rooms
    ]


@router.get("/{room_id}", response_model=RoomOut)
def get_room(room_id: int, db: Session = Depends(get_db)):
    room = db.get(Room, room_id)
    if room is None:
        raise HTTPException(status_code=404, detail="Room not found")
    return room


@router.post("", response_model=RoomOut, status_code=201)
def create_room(payload: RoomIn, db: Session = Depends(get_db)):
    room = Room(name=payload.name, capacity=payload.capacity)
    db.add(room)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="A room with that name already exists")
    return room


@router.post("/{room_id}/suggest", response_model=SuggestOut)
def suggest_slots(room_id: int, payload: SuggestIn, db: Session = Depends(get_db)):
    room = db.get(Room, room_id)
    if room is None:
        raise HTTPException(status_code=404, detail="Room not found")
    requester = db.get(User, payload.requester_id)
    if requester is None:
        raise HTTPException(status_code=404, detail="Requester not found")

    attendee_ids = set(payload.attendee_ids)
    attendees = db.scalars(select(User).where(User.id.in_(attendee_ids))).all()
    if len(attendees) != len(attendee_ids):
        raise HTTPException(status_code=400, detail="Unknown attendee")

    if not can_book(requester.role, room.name):
        raise HTTPException(
            status_code=403,
            detail=messages.restricted_room(requester.name, requester.role, room.name),
        )

    slots = find_slots(
        payload.date,
        payload.duration_minutes,
        room_name=room.name,
        requester_role=requester.role,
        after=payload.after,
        room_bookings=room_bookings(db, room.id, payload.date),
        people_bookings=people_bookings(db, attendee_ids | {requester.id}, payload.date),
    )
    return SuggestOut(slots=[SlotOut(start=start, end=end) for start, end in slots])
