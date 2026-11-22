# Decisions

## Assumptions

### Task 1

- Times are half-open intervals, as the office rules say. A booking can start at the exact minute another one ends.

### Task 2

- The cleaning buffer only blocks the room. People can go straight from one meeting into the next.
- The buffer can run past 18:30. A meeting that ends at 18:30 still gets its cleaning time afterwards.
- A new meeting's cleaning time has to fit before the next booking in the same room. For example, a 75-minute meeting ending at 17:30 is refused if the room is booked from 17:30, because there would be no time to clean.
- Cleaning time doesn't count towards the lunch rule. A 11:45–13:00 meeting is allowed even though the room is being cleaned from 13:00 to 13:15.
- "Longer than 60 minutes" means strictly longer: a 60-minute meeting gets no buffer, a 75-minute one does.
- The person asking for slots is treated as an attendee, so their own calendar is checked too.
- The intern rule applies to the person making the booking. An intern can still attend a Board Room meeting that someone else booked.
- Asking for slots on a weekend returns no slots rather than an error.
- A time sent without a timezone is read as IST. A time sent with a timezone is converted to IST. Times that aren't on a 15-minute boundary, or that include seconds, are rejected (422) instead of being quietly rounded.
- Suggestions don't look at the current time, so the same request always gives the same answer, and a past date still returns slots.

## Trade-offs

- **Office rules live in one object.** Every rule (working hours, lunch, buffer, which roles can use which rooms, and so on) is a field on a single `Policy` in `backend/app/rules.py`, and the functions that check bookings take it as an argument. I kept the rules in code rather than in environment variables or a database table, so changing a rule goes through review and tests like any other change. If rules ever need to differ per office, a `Policy` can be built from a database row without changing the checking code.
- **One function decides whether a slot is valid.** `slot_violations` in `backend/app/scheduling.py` lists every rule a slot breaks. Both `/suggest` and `POST /bookings` use it, so the API can't accept a booking that `/suggest` would treat as invalid. Task 2 only asks for `/suggest`, but without the same checks on `POST /bookings` the suggestions would just be advice and anything could still be booked.
- **Each booking stores when its room is free again.** `room_free_at` is the end time plus any cleaning buffer, saved when the booking is made. That makes "is the room free?" a simple comparison, and PR 3 needs it as a column to stop double bookings in the database itself. The downside: if the buffer rule changes, existing bookings keep the old value, and updating them could create clashes that someone would have to sort out by hand.
- **Times are stored as plain IST.** The database holds IST times without a timezone, and responses always add `+05:30`. India has had no daylight saving since 1945, so a fixed offset is always right, and it avoids needing a timezone database (Windows doesn't ship one).
- **Interns asking for the Board Room get a 403, not an empty list.** The spec lists the intern rule alongside the other slot rules, which hints at an empty list. I return 403 because it tells the user "you can never book this room" instead of "nothing is free today".
- **When a booking breaks several rules, the answer is 403, then 422, then 409.** "You can't use this room" comes first, then "this request is invalid" (weekend, lunch, outside hours), and only then "someone already has that time". It's misleading to say a time is taken when the booking could never have been made anyway. One exception: a few checks happen while FastAPI reads the request, before any of this runs (times not on a 15-minute boundary, times with seconds, an end before the start, and `/suggest`'s duration). Those always return 422, even if the room or user doesn't exist, and their error message is a list rather than a single string.
- **The Board Room is identified by its name**, as the spec describes it. A "restricted" flag on the room would be safer, because renaming the room would currently drop the restriction.

## Other problems

Problems I found while reading the starter code, most serious first. Each one says where it is and whether a later PR fixes it. The ones without a fix are still open.

- **High**: incoming times lose their timezone without being converted (`replace(tzinfo=None)`), so 10:00 UTC is saved as 10:00 IST, and responses have no timezone. Fixed in PR 2: times are converted to IST on the way in and always sent back with `+05:30` (`backend/app/office_time.py:12`).
- **High**: `create_booking` checks for a clash and then saves, so two requests at the same moment can both pass the check and both be saved. `backend/app/routers/bookings.py:82-108`. Planned for PR 3.
- **High**: `POST /bookings` doesn't check attendees, working hours, weekdays, the 15-minute grid, meeting length or the intern rule, so it accepts bookings the office rules forbid. Fixed in PR 2: it now runs the same checks as `/suggest` (`backend/app/routers/bookings.py:82`).
- **Medium**: the booking list can show the wrong day. Requests are slowed down on purpose (up to 800 ms), so if you click through dates quickly, an older response can arrive last and replace the newer one. The list also keeps showing the previous day's bookings while a new day loads or after an error. `frontend/src/components/BookingList.jsx:10-17`. Planned for PR 4.
- **Medium**: the API trusts whatever `creator_id` it's sent, so anyone can book as anyone, and the creator wasn't added as an attendee. `backend/app/schemas.py:31`. The attendee part is fixed in PR 2 (`backend/app/routers/bookings.py:79`). Checking who is really making the request is still open.
- **Medium**: nothing checks that the attendees fit in the room. `backend/app/routers/bookings.py:75-80`.
- **Low**: checking for a clash loaded every booking the room ever had. Fixed in PR 2: only that day's bookings are loaded (`backend/app/availability.py:14`).
- **Low**: a user's role could be any text. Fixed in PR 2: roles are a fixed list, enforced by the database too (`backend/app/models.py:23`).
- **Low**: there are no database migrations; tables are created on startup. After pulling a change to the tables you have to re-run the seed script. `backend/app/main.py:17`.
- **Low**: seconds were quietly dropped from times, before the "end must be after start" check, so a 10:00:10–10:00:50 booking got that confusing error. Fixed in PR 2: times with seconds are rejected with a clear message (`backend/app/office_time.py:20`).
- **Low**: `GET /bookings?date=` lists bookings that *start* on that day (`backend/app/routers/bookings.py:28-30`), while the booking checks look at anything that *overlaps* the day (`backend/app/availability.py:14`). A booking running past midnight would only be listed on its first day. The working-hours rule stops such bookings being made today.
- **Low**: the 15-minute grid counts from the top of the hour, not from opening time (`backend/app/scheduling.py:57`). With today's 09:30 opening that makes no difference, but if opening time were changed to, say, 09:10, no slot would ever be suggested.
- **Low**: bookings can be made in the past. `backend/app/routers/bookings.py:66-110`.
- **Low**: `npm audit` reports one high and one moderate issue in vite 5 / esbuild. They only affect the local dev server. `frontend/package.json:17`. `npm audit fix --force` would jump to a new major version of vite, so I left it.
- **Low**: the frontend only shows error messages that are plain strings, so validation errors (whose message is a list) show up as just "Request failed (422)". `frontend/src/api.js:7`. Planned for PR 4.
- **Low**: the README setup commands were for macOS/Linux only. `README.md:18`. Fixed in PR 1: each command now has its Windows equivalent next to it.

## With more time

- To be written once all four tasks are done.

## AI usage

### Task 1

- Claude Code wrote the test and the fix. I reviewed and approved each step before it was committed.
- The first version of the test booked the Focus Room at 11:30, right after a 90-minute meeting. Once the cleaning buffer from Task 2 exists, that booking is correctly refused, so the test would start failing for a good reason. I moved it to the slot right after a 30-minute meeting, which has no buffer.

### Task 2

- **How I used it:** I used Claude Code in three roles. One session wrote the code (Sonnet). A second session, which never saw the first one's reasoning, reviewed every step before it was committed (Opus). I read each step's changes and test results and approved it. The reviewer also broke the code on purpose in small ways to check that the tests would catch it (mutation testing).
- **Where the AI was wrong:** the plan Claude drafted said to test "cleaning time doesn't count towards lunch" with an 11:30–12:45 meeting. Its cleaning ends exactly at 13:00, so it never touches lunch and the test could never fail. The reviewer found it by breaking the lunch check and seeing every test still pass. The test now uses 11:45–13:00.
- **Where the AI was wrong:** a test helper pulled the database session out of FastAPI's internals, and another test assumed the sample bookings had ids 1 to 12. I rejected both as hacks; they now use a proper test fixture and look bookings up by title.
- **Where the AI was wrong:** the first version of the code that formats times stamped `+05:30` onto times that already had a timezone instead of converting them, which would have shown them 5.5 hours off. The reviewer caught it before it was committed.
