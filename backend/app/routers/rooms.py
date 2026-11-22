from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..availability import people_bookings, room_bookings
from ..db import get_db
from ..models import Room, User
from ..rules import can_book
from ..scheduling import find_slots
from ..schemas import RoomIn, RoomOut, SlotOut, SuggestIn, SuggestOut

router = APIRouter(prefix="/rooms", tags=["rooms"])


@router.get("", response_model=list[RoomOut])
def list_rooms(db: Session = Depends(get_db)):
    return db.scalars(select(Room).order_by(Room.id)).all()


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
            detail=f"{requester.name} ({requester.role.value}) can't book the {room.name}",
        )

    slots = find_slots(
        payload.date,
        payload.duration_minutes,
        room_name=room.name,
        requester_role=requester.role,
        room_bookings=room_bookings(db, room.id, payload.date),
        people_bookings=people_bookings(db, attendee_ids | {requester.id}, payload.date),
    )
    return SuggestOut(slots=[SlotOut(start=start, end=end) for start, end in slots])
