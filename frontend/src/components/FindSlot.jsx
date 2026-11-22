import { useEffect, useRef, useState } from "react";
import { getRooms, getUsers, suggestSlots } from "../api.js";
import { formatTime } from "../dates.js";

const DURATIONS = Array.from({ length: 16 }, (_, i) => (i + 1) * 15);
const IDLE = { status: "idle", slots: [], error: null };

export default function FindSlot({ initialDate }) {
  const [users, setUsers] = useState(null);
  const [rooms, setRooms] = useState({ requesterId: "", list: [] });
  const [loadError, setLoadError] = useState(null);
  const [requesterId, setRequesterId] = useState("");
  const [roomId, setRoomId] = useState("");
  const [attendeeIds, setAttendeeIds] = useState([]);
  const [duration, setDuration] = useState(30);
  const [date, setDate] = useState(initialDate);
  const [result, setResult] = useState(IDLE);
  const latestRequest = useRef(0);

  useEffect(() => {
    getUsers()
      .then((list) => {
        setUsers(list);
        setLoadError(null);
      })
      .catch((err) => setLoadError(err.message));
  }, []);

  useEffect(() => {
    if (!requesterId) return;
    let ignore = false;
    getRooms(requesterId)
      .then((list) => {
        if (ignore) return;
        setRooms({ requesterId, list });
        setLoadError(null);
        setRoomId((current) =>
          list.some((room) => String(room.id) === current && room.bookable) ? current : ""
        );
      })
      .catch((err) => {
        if (!ignore) setLoadError(err.message);
      });
    return () => {
      ignore = true;
    };
  }, [requesterId]);

  const people = users ?? [];
  const requester = people.find((user) => String(user.id) === requesterId);
  const roomsReady = rooms.requesterId === requesterId;
  const roomPlaceholder = !requesterId
    ? "Choose who is booking first"
    : roomsReady
      ? "Choose a room"
      : "Loading rooms…";
  const roomOptions = roomsReady ? rooms.list : [];
  const canSubmit = requesterId && roomsReady && roomId && duration && date;
  const loading = result.status === "loading";

  function changeInput(update) {
    latestRequest.current += 1;
    setResult(IDLE);
    update();
  }

  function toggleAttendee(id) {
    changeInput(() =>
      setAttendeeIds((ids) => (ids.includes(id) ? ids.filter((i) => i !== id) : [...ids, id]))
    );
  }

  function changeRequester(value) {
    changeInput(() => {
      setRequesterId(value);
      setLoadError(null);
      if (!value) setRoomId("");
      setAttendeeIds((ids) => ids.filter((id) => String(id) !== value));
    });
  }

  function submit(event) {
    event.preventDefault();
    const request = ++latestRequest.current;
    setResult({ status: "loading", slots: [], error: null });
    suggestSlots(roomId, {
      requesterId: Number(requesterId),
      attendeeIds,
      durationMinutes: Number(duration),
      date,
    })
      .then((data) => {
        if (request === latestRequest.current) {
          setResult({ status: "done", slots: data.slots, error: null });
        }
      })
      .catch((err) => {
        if (request === latestRequest.current) {
          setResult({ status: "error", slots: [], error: err.message });
        }
      });
  }

  return (
    <section className="card find-slot">
      <h2>Find a slot</h2>
      <form onSubmit={submit}>
        <div className="form-grid">
          <label>
            Booking as
            <select value={requesterId} onChange={(e) => changeRequester(e.target.value)}>
              <option value="">Choose a person</option>
              {people.map((user) => (
                <option key={user.id} value={user.id}>
                  {user.name} ({user.role})
                </option>
              ))}
            </select>
          </label>
          <label>
            Room
            <select
              value={roomId}
              disabled={!requesterId || !roomsReady}
              onChange={(e) => changeInput(() => setRoomId(e.target.value))}
            >
              <option value="">{roomPlaceholder}</option>
              {roomOptions.map((room) => (
                <option key={room.id} value={room.id} disabled={!room.bookable}>
                  {room.bookable
                    ? room.name
                    : `${room.name} (not available to ${requester.role}s)`}
                </option>
              ))}
            </select>
          </label>
          <label>
            Duration
            <select
              value={duration}
              onChange={(e) => changeInput(() => setDuration(Number(e.target.value)))}
            >
              {DURATIONS.map((minutes) => (
                <option key={minutes} value={minutes}>
                  {minutes} min
                </option>
              ))}
            </select>
          </label>
          <label>
            Date
            <input
              type="date"
              value={date}
              onChange={(e) => changeInput(() => setDate(e.target.value))}
            />
          </label>
        </div>
        <fieldset>
          <legend>Attendees</legend>
          <div className="attendees">
            {people
              .filter((user) => String(user.id) !== requesterId)
              .map((user) => (
                <label key={user.id} className="checkbox">
                  <input
                    type="checkbox"
                    checked={attendeeIds.includes(user.id)}
                    onChange={() => toggleAttendee(user.id)}
                  />
                  {user.name}
                </label>
              ))}
          </div>
        </fieldset>
        <button type="submit" disabled={!canSubmit || loading}>
          Find slots
        </button>
      </form>
      <div className="results" aria-live="polite">
        {users === null && !loadError && <p className="muted">Loading…</p>}
        {loadError && <p className="error">{loadError}</p>}
        {loading && <p className="muted">Finding slots…</p>}
        {result.status === "error" && <p className="error">{result.error}</p>}
        {result.status === "done" && result.slots.length === 0 && (
          <p className="muted">No free slots on that day. Try another date, duration or room.</p>
        )}
        {result.slots.length > 0 && (
          <ul className="slots">
            {result.slots.map((slot) => (
              <li key={slot.start}>
                <span className="time">
                  {formatTime(slot.start)}–{formatTime(slot.end)}
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}
