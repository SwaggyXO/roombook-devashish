const BASE = "/api";

export class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

function itemMessage(item) {
  if (typeof item?.msg !== "string") return null;
  if (item.msg.startsWith("Value error, ")) return item.msg.slice("Value error, ".length);
  const field = Array.isArray(item.loc) ? item.loc.at(-1) : null;
  return typeof field === "string" ? `${field}: ${item.msg}` : item.msg;
}

function errorMessage(detail, status) {
  if (typeof detail === "string" && detail) return detail;
  if (Array.isArray(detail)) {
    const messages = detail.map(itemMessage).filter(Boolean);
    if (messages.length) return messages.join("; ");
  }
  return `Request failed (${status})`;
}

async function request(path, options) {
  const res = await fetch(BASE + path, options);
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new ApiError(errorMessage(body.detail, res.status), res.status);
  }
  return res.json();
}

export const getRooms = (userId) =>
  request(userId == null ? "/rooms" : `/rooms?user_id=${encodeURIComponent(userId)}`);

export const getUsers = () => request("/users");

export const getBookings = (date) => request(`/bookings?date=${date}`);

export const createBooking = (booking) =>
  request("/bookings", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(booking),
  });

export const suggestSlots = (roomId, { requesterId, attendeeIds, durationMinutes, date, after }) =>
  request(`/rooms/${roomId}/suggest`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      requester_id: requesterId,
      attendee_ids: attendeeIds,
      duration_minutes: durationMinutes,
      date,
      after,
    }),
  });
