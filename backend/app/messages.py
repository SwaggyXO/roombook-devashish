from .roles import Role

ROOM_ALREADY_BOOKED = "Room is already booked for that time"
ATTENDEE_ALREADY_BOOKED = "An attendee is already booked at that time"


def restricted_room(user_name: str, role: Role, room_name: str) -> str:
    return f"{user_name} ({role.value}) can't book the {room_name}"
