import { formatTime } from "../dates.js";

export default function SlotList({
  slots,
  pageNumber,
  hasNext,
  roomName,
  action,
  onBook,
  onPrevious,
  onNext,
}) {
  const busy = action !== null;

  return (
    <>
      <ul className="slots">
        {slots.map((slot) => {
          const range = `${formatTime(slot.start)}–${formatTime(slot.end)}`;
          const booking = action?.type === "book" && action.start === slot.start;
          return (
            <li key={slot.start}>
              <span className="time">{range}</span>
              <button
                type="button"
                aria-label={`Book ${roomName} ${range}`}
                disabled={busy}
                onClick={() => onBook(slot)}
              >
                {booking ? "Booking…" : "Book"}
              </button>
            </li>
          );
        })}
      </ul>
      {(pageNumber > 1 || hasNext) && (
        <nav className="pager" aria-label="Pages of free slots">
          <button
            type="button"
            className="secondary"
            disabled={busy || pageNumber === 1}
            onClick={onPrevious}
          >
            ← Previous
          </button>
          <span>Page {pageNumber}</span>
          <button
            type="button"
            className="secondary"
            disabled={busy || !hasNext}
            onClick={onNext}
          >
            {action?.type === "next" ? "Loading…" : "Next →"}
          </button>
        </nav>
      )}
    </>
  );
}
