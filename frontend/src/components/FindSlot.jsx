import { useEffect, useRef, useState } from "react";
import { createBooking, getRooms, getUsers, suggestSlots } from "../api.js";
import { formatTime } from "../dates.js";
import SlotList from "./SlotList.jsx";

const DURATIONS = Array.from({ length: 16 }, (_, i) => (i + 1) * 15);
const BOOKING_TITLE = "Meeting";
const IDLE = { status: "idle", pages: [], index: 0, error: null };

export default function FindSlot({ initialDate, onBookingsChanged }) {
  const [users, setUsers] = useState(null);
  const [rooms, setRooms] = useState({ requesterId: "", list: [] });
  const [loadError, setLoadError] = useState(null);
  const [requesterId, setRequesterId] = useState("");
  const [roomId, setRoomId] = useState("");
  const [attendeeIds, setAttendeeIds] = useState([]);
  const [duration, setDuration] = useState(30);
  const [date, setDate] = useState(initialDate);
  const [result, setResult] = useState(IDLE);
  const [notice, setNotice] = useState(null);
  const [action, setAction] = useState(null);
  const latestRequest = useRef(0);
  const noticeRef = useRef(null);

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

  useEffect(() => {
    if (notice) noticeRef.current?.focus();
  }, [notice]);

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
  const currentPage = result.pages[result.index];
  const busy = loading || action !== null;

  function changeInput(update) {
    latestRequest.current += 1;
    setResult(IDLE);
    setNotice(null);
    setAction(null);
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

  function findSlots(after) {
    return suggestSlots(roomId, {
      requesterId: Number(requesterId),
      attendeeIds,
      durationMinutes: Number(duration),
      date,
      after,
    });
  }

  function loadFirstPage(request) {
    setAction(null);
    setResult({ ...IDLE, status: "loading" });
    findSlots()
      .then((data) => {
        if (request !== latestRequest.current) return;
        const page = { slots: data.slots, hasMore: data.has_more };
        setResult({ status: "done", pages: [page], index: 0, error: null });
      })
      .catch((err) => {
        if (request !== latestRequest.current) return;
        setResult({ ...IDLE, status: "error", error: err.message });
      });
  }

  function submit(event) {
    event.preventDefault();
    setNotice(null);
    loadFirstPage(++latestRequest.current);
  }

  function previousPage() {
    setResult((prev) => ({ ...prev, index: prev.index - 1 }));
  }

  function nextPage() {
    if (result.index + 1 < result.pages.length) {
      setResult((prev) => ({ ...prev, index: prev.index + 1 }));
      return;
    }
    const request = ++latestRequest.current;
    setAction({ type: "next" });
    setResult((prev) => ({ ...prev, error: null }));
    findSlots(currentPage.slots.at(-1).start)
      .then((data) => {
        if (request !== latestRequest.current) return;
        setAction(null);
        if (data.slots.length === 0) {
          setResult((prev) => {
            const pages = [...prev.pages];
            pages[prev.index] = { ...pages[prev.index], hasMore: false };
            return { ...prev, pages };
          });
          setNotice("No more free slots that day.");
          return;
        }
        const page = { slots: data.slots, hasMore: data.has_more };
        setResult((prev) => ({ ...prev, pages: [...prev.pages, page], index: prev.index + 1 }));
      })
      .catch((err) => {
        if (request !== latestRequest.current) return;
        setResult((prev) => ({ ...prev, error: err.message }));
        setAction(null);
      });
  }

  function book(slot) {
    const request = ++latestRequest.current;
    const roomName = roomOptions.find((room) => String(room.id) === roomId).name;
    setAction({ type: "book", start: slot.start });
    setNotice(null);
    setResult((prev) => ({ ...prev, error: null }));
    createBooking({
      room_id: Number(roomId),
      creator_id: Number(requesterId),
      title: BOOKING_TITLE,
      attendee_ids: attendeeIds,
      start: slot.start,
      end: slot.end,
    })
      .then(() => {
        onBookingsChanged(date);
        setAction(null);
        if (request === latestRequest.current) setResult(IDLE);
        setNotice(
          `Booked ${roomName} ${formatTime(slot.start)}–${formatTime(slot.end)} on ${date}.`
        );
      })
      .catch((err) => {
        setAction(null);
        if (err.status === 409) {
          onBookingsChanged(date);
          setNotice(`That slot is no longer free: ${err.message}. Here are the latest free slots.`);
          loadFirstPage(++latestRequest.current);
        } else {
          setResult((prev) => ({ ...prev, error: err.message }));
        }
      });
  }

  return (
    <section className="card find-slot">
      <h2>Find a slot</h2>
      <form onSubmit={submit}>
        <fieldset className="controls" disabled={busy}>
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
          <button type="submit" disabled={!canSubmit}>
            Find slots
          </button>
        </fieldset>
      </form>
      <div className="results" aria-live="polite">
        {users === null && !loadError && <p className="muted">Loading…</p>}
        {loadError && <p className="error">{loadError}</p>}
        {loading && <p className="muted">Finding slots…</p>}
        {notice && (
          <p ref={noticeRef} tabIndex={-1}>
            {notice}
          </p>
        )}
        {result.error && <p className="error">{result.error}</p>}
        {currentPage && currentPage.slots.length === 0 && (
          <p className="muted">No free slots on that day. Try another date, duration or room.</p>
        )}
        {currentPage && currentPage.slots.length > 0 && (
          <SlotList
            slots={currentPage.slots}
            pageNumber={result.index + 1}
            hasNext={currentPage.hasMore}
            roomName={roomOptions.find((room) => String(room.id) === roomId)?.name}
            action={action}
            onBook={book}
            onPrevious={previousPage}
            onNext={nextPage}
          />
        )}
      </div>
    </section>
  );
}
