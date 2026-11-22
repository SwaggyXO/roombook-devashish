# Decisions

## Assumptions

- Task 1: intervals are half-open, per the office rules. A booking may start exactly when another one ends.

## Trade-offs

- Filled in as tasks land.

## Other problems

Noticed while reading the code. Not fixed in Task 1 unless a task is named.

- **High**: the timezone offset is dropped without converting the time (`replace(tzinfo=None)`), and responses come back naive. `backend/app/schemas.py:39`. Planned for PR 2.
- **High**: `create_booking` checks for a clash and then inserts, so two requests can both pass the check. `backend/app/routers/bookings.py:47-61`. Planned for PR 3.
- **High**: `POST /bookings` skips the attendee clash check, working hours, weekday, grid, duration and the intern rule, so the API accepts bookings the office rules forbid. `backend/app/routers/bookings.py:35-63`. Planned for PR 2.
- **Medium**: `BookingList` can show the wrong day. Under the simulated GET latency, a slow response for an earlier date can arrive after a newer one and overwrite it. The list is also not cleared when the date changes or a request fails, so the previous day's bookings show under the new date while loading (up to 800 ms of simulated latency) or after an error. `frontend/src/components/BookingList.jsx:10-17`. Planned for PR 4.
- **Medium**: `creator_id` comes from the client with no identity check, and the creator is not added as an attendee. `backend/app/schemas.py:30`, `backend/app/routers/bookings.py:39-59`. The attendee part is planned for PR 2.
- **Medium**: room capacity is not checked against the number of attendees. `backend/app/routers/bookings.py:42-45`.
- **Low**: the overlap check loads every booking for the room into Python. `backend/app/routers/bookings.py:47-50`.
- **Low**: `role` is a free string in the database. `backend/app/models.py:21`.
- **Low**: no migrations; tables are made with `create_all`. `backend/app/main.py:17`.
- **Low**: seconds are silently truncated from start and end. Because they are dropped before the end-after-start check, a 10:00:10–10:00:50 booking gets the misleading error "end must be after start". `backend/app/schemas.py:39-44`.
- **Low**: bookings in the past are allowed. `backend/app/routers/bookings.py:35-63`.
- **Low**: `npm audit` reports 1 high and 1 moderate issue in vite 5 / esbuild (dev server only). `frontend/package.json:17`. `npm audit fix --force` would jump a major version.
- **Low**: `frontend/src/api.js:7` ignores the list-shaped `detail` that FastAPI returns for 422 validation errors, so the user sees only "Request failed (422)". Planned for PR 4.
- **Low**: the README setup is bash-only. `README.md:18`. Fixed in this PR (Windows hints added inline).

## With more time

- Filled in as tasks land.

## AI usage

### Task 1

- Claude Code wrote the test and fix; I reviewed and approved each step before it was committed.
- The first version of the test used Focus Room 11:30–12:00, right after a 90-minute meeting. Once the cleaning-buffer rule lands, that booking is correctly rejected, so the "test that would have caught it" would start failing for a valid reason. I switched it to a back-to-back pair after a 30-minute meeting.
