# Implemented MVP contract

## Scope and request rules

The backend is Flask/Pydantic 2. Requests reject unknown fields and blank identifiers.
Dates must be ISO calendar strings; timestamps must be ISO strings rather than
numeric epochs. Boolean and travel-minute inputs are strict. Monetary values use
finite, nonnegative Decimal values with at most two decimal places. Null cost means
unknown, not free. The prototype supports USD and trips of at most 14 days, within
1900–2100. Model errors return 422 with structured `detail` entries.

## Core models

| Model | Fields |
| --- | --- |
| Location | `id`, `name`, optional paired `latitude`/`longitude` |
| Activity | `id`, `name`, `location`, aware `start_time`/`end_time`, optional `estimated_cost`, `priority` (low/medium/high), `fixed` |
| Trip | `destination`, `start_date`, `end_date`, IANA `timezone`, optional `budget`, `currency=USD`, `preferences=[]`, `activities` |
| TravelTime | `from_location_id`, `to_location_id`, strict integer `minutes>=0` |
| OpeningWindow | aware `start_time`, aware `end_time`, positive duration |
| OpeningHours | `location_id`, authoritative concrete `windows` for the trip period |

Activity IDs, original fixed-event IDs, directed fact pairs and opening-location
records must be unique. Fact references must appear in the candidate or original
baseline. Omit same-location travel facts; their required transfer time is zero.
Travel directions are independent. Candidate activity intervals can be parseable
but nonpositive; that is a semantic violation. Invalid opening fact intervals are
malformed input instead.

## POST /validate

Input: `ValidationRequest` containing:

- `trip`: the candidate Trip.
- `original_fixed_events`: required authoritative Activity list, including `[]`
  when there are no fixed commitments. Every original event must have `fixed=true`.
- `travel_times`: optional list, default `[]`.
- `opening_hours`: optional list, default `[]`.

See [complete valid example](../examples/validate-valid.json).

HTTP 200 returns `is_valid`, `violations`, and `warnings`. Issues contain a stable
`code`, `activity_ids`, and human-readable `message`. `is_valid` is exactly whether
there are no violations. It is not a guarantee about unknown facts; warnings remain
visible and must not be hidden by a passing boolean. Lists sort by code and ID tuple.

| Violation | Behavior |
| --- | --- |
| FIXED_EVENT_MISSING | An original commitment's ID is absent |
| FIXED_EVENT_MOVED | Its UTC start or end instant changed |
| FIXED_EVENT_CHANGED | Its name/location/fixed flag changed |
| UNEXPECTED_FIXED_EVENT | Candidate declares a fixed event absent from the baseline |
| INVALID_INTERVAL | Candidate end <= start |
| ACTIVITY_OUTSIDE_TRIP | Positive interval extends outside the local trip dates |
| OVERLAP | Every pair with `max(starts) < min(ends)` |
| INSUFFICIENT_TRAVEL_TIME | Consecutive gap < known directed travel duration |
| CLOSED_LOCATION | Known opening windows do not cover the whole visit |
| BUDGET_EXCEEDED | Known activity estimates alone exceed the optional budget |

Warnings: `MISSING_TRAVEL_TIME`, `MISSING_OPENING_HOURS`, `MISSING_COST_DATA`, and
`TRAVEL_CHECK_SKIPPED`. Unknown costs warn only when a budget is requested. Known
costs can already prove an overrun even when other costs remain unknown. Every cost
counts once, including fixed events and invalid-interval candidates.

## Time and coverage semantics

Compare instants and elapsed durations in UTC. Inclusive trip dates become local
midnight on the first date through midnight after the final date. An activity may
end exactly at that upper bound. Half-open activity intervals make adjacency valid;
travel can still fail. Exact travel/budget equality passes; seconds are not rounded
up by the validator. OSRM's seconds are conservatively rounded up when creating
integer-minute provider facts.

Offset timestamps can use a different offset from the trip zone. For the planning
form, naive datetime-local inputs use the explicit trip timezone. Ambiguous or
nonexistent DST wall times are rejected; clients can supply an explicit UTC offset
through JSON. The validator itself always requires aware times. Live weekly opening tags use the destination timezone and destination calendar dates, even when the trip display timezone differs.

Nonpositive candidates are excluded from overlap, opening and trip-bound checks.
Travel is skipped with one warning whenever any interval is nonpositive or any
activities overlap. Otherwise it evaluates sorted consecutive pairs without changing
input order. Same-place legs require zero minutes; unknown different-place legs warn.

Touching/overlapping opening windows are merged. Visits must fit completely in a
merged window, including exact opening/closing boundaries. `windows=[]` means closed
throughout the trip; no record means unknown and warns once per location.

## POST /api/plan

Input fields: `destination`, `start_date`, `end_date`, `timezone` (default
`America/Chicago`), `preferences=[]`, `requested_places=[]` (at most 3),
`fixed_events=[]` (at most 10), optional `budget`, `data_mode=demo|live`, and
`planner=heuristic`. The defaults are demo and heuristic.

Each fixed form event has `id`, `name`, `location` text, start/end ISO timestamps
(local in the trip zone or explicit offsets), and optional paired coordinates.
Its interval must be positive and inside the trip. The server retains a separate
original baseline before generation. Demo mode supports Chicago only.

Output contains:

- `request`: a complete ValidationRequest, reusable with `/validate`.
- `validation`: the independent result.
- `fully_checked`: whether validation has no missing/skipped-check warnings.
- `data_mode`, `planner`, `notes`, `unscheduled_places`, and `attributions`.

`fully_checked` describes coverage of supplied facts, not provider correctness or
completion of every desired visit. Unscheduled places and provider notes must be
read alongside it. Demo facts are synthetic even when all checks pass. A valid
empty itinerary is allowed by `/validate`; the planner explicitly lists visits it
could not schedule.

Essential provider failures return 503; unsupported planner names return 422;
there is no automatic substitution of demo data. Missing routing can yield a
partially checked candidate with warnings. Malformed JSON returns 400, wrong content
type 415, oversized input 413. Unexpected programming errors remain server errors.

Other endpoints: `GET /` serves the page; `GET /api/health` reports capability flags
without keys; `GET /api/example` supplies the synthetic starter request. Health does
not make external calls or prove live-provider availability.

## Progress and source fields

`POST /api/plan` also returns `research_steps`, `sources`, and `preparation`. A step
has an ID, title, status, detail, provider, optional public URL, data mode and an
explicit `network_request` flag. Actual calls can be running/completed/failed; cache
hits are marked cached. Demo fact loading is marked example and makes no web claim.

A source card preserves the reported opening expression, its parsing/coverage state,
a map-record URL and an optional website tag. `website_checked=false` means the
venue site was not fetched. Preparation items have `booking_required=null` and
`availability_checked=false`; they suggest checks without asserting inventory.

`POST /api/plan/stream` accepts the same input and returns newline-delimited JSON.
`type=progress` updates one step; `type=result` provides the complete response;
`type=error` includes an explanatory message and status. Heartbeats carry no work
claim. Shape errors return ordinary HTTP 422 before streaming begins. Once a stream
has started, service/validation errors are terminal error events inside HTTP 200.
The browser renders them as failures. At most two streamed plans run concurrently.
Client disconnects stop work at the next observation; individual provider calls
still have bounded timeouts. Streams expire after 180 seconds.
