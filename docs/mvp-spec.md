# First MVP specification

## Goal and completion

Deliver an offline, deterministic `POST /validate` backend. Given a structured trip
and optional factual inputs, it reports all applicable constraint violations and
warns about unavailable checks. Models, rules, and HTTP behavior below are planned;
none are implemented by this documentation change.

The milestone is complete when all required cases in [test-plan.md](test-plan.md)
pass against the pure validator and API as applicable. AI, repair, external APIs,
storage, UI, and authentication are out of scope.

## Schema conventions

Target Pydantic 2. Use `extra="forbid"` on request models to catch misspelled fields.
Required fields have no default. Trim surrounding whitespace in identifiers and
display text and reject empty strings. IDs are case-sensitive and unique within
their documented scope. Lists default with `default_factory`, never shared mutable
instances. Require actual JSON booleans for `fixed` and actual JSON integers for
travel minutes; do not coerce `true` to `1`.

Use `Decimal` with at most two decimal places for money, finite and nonnegative.
The canonical JSON representation is a decimal string such as `"35.00"`; finite
JSON numbers with at most two decimal places may also be parsed, but no subsequent
arithmetic may use floats. Reject excessive precision rather than silently rounding.

### Trip

| Field | Type / default | Meaning and constraints |
| --- | --- | --- |
| `destination` | nonempty string | Human-readable destination |
| `start_date` | ISO date, required | First included local calendar date |
| `end_date` | ISO date, required | Last included local calendar date; must be >= start |
| `timezone` | IANA timezone string, required | Validate with `zoneinfo.ZoneInfo`, e.g. `America/Chicago` |
| `currency` | literal `USD`, default `USD` | MVP uses USD only; no exchange rates |
| `budget` | money, required | Total activity-estimate ceiling |
| `preferences` | list of nonempty strings, default `[]` | Descriptive input; no validation or ranking effect yet |
| `activities` | list of Activity, required | IDs must be unique; empty list is permitted |

Dates are inclusive. The permitted instant range is `[start_date at local midnight,
day after end_date at local midnight)`. Activities may end exactly at the exclusive
upper boundary. Reject an `end_date` without a representable next day as malformed
input. An empty itinerary is valid with zero cost and no missing-data warnings.

### Activity

| Field | Type / default | Meaning and constraints |
| --- | --- | --- |
| `id` | nonempty string, required | Stable unique ID within a trip |
| `name` | nonempty string, required | Display name |
| `location` | Location, required | `{ "id": "museum", "name": "Museum" }` |
| `start_time` | offset-aware ISO datetime, required | Beginning of activity |
| `end_time` | offset-aware ISO datetime, required | End of activity |
| `estimated_cost` | money, required | Cost in the trip currency |
| `priority` | `low`, `medium`, or `high`; default `medium` | Future planning/repair hint; no rule effect |
| `fixed` | strict boolean, default `false` | Future repair may not move this commitment |

Location contains required nonempty `id` and `name` strings. Repeated location IDs
refer to the same place even if display names differ; names do not determine travel.
Coordinates and addresses are deferred. Positive duration is a semantic rule, so a
parseable activity with `end_time <= start_time` reaches the validator and produces
`INVALID_INTERVAL`, not HTTP 422.

### ValidationRequest and optional facts

| Field | Type / default | Meaning |
| --- | --- | --- |
| `trip` | Trip, required | Candidate to evaluate |
| `travel_times` | list of TravelTime, default `[]` | Known directed durations |
| `opening_hours` | list of OpeningHours, default `[]` | Known opening windows for the trip |

`TravelTime` has `from_location_id`, `to_location_id` (nonempty strings) and
`minutes` (strict integer >= 0). Reject duplicate directed pairs, including equal
values, to avoid ambiguous sources. A→B does not imply B→A. Each fact's location ID
must appear in the trip. Same-location transfers always require zero minutes;
reject explicit self-pair facts to avoid conflicting definitions. A different-place
duration of zero is allowed when explicitly supplied.

`OpeningHours` has `location_id` and required `windows: list[OpeningWindow]`.
Each window has `start_time` and `end_time`, both offset-aware, and must have positive
duration. Bad fact windows produce 422, unlike bad activity intervals. Reject duplicate
opening records for the same location and unknown location IDs. Windows may extend
outside trip bounds (e.g. an overnight opening period).

An opening record is an authoritative list of available windows for the entire trip
period. An empty `windows` list explicitly means closed throughout that period.
Omitting the record means unknown, not closed. The caller must not present an
incomplete day's provider data as complete coverage. Live provider freshness,
holidays, and provenance are deferred.

## Time and boundary policy

- Require `Z` or an explicit numeric UTC offset on all timestamps. Naive datetimes
  and invalid IANA zones are request errors (422).
- JSON timestamps must be ISO strings, not numeric epochs; trip dates must be ISO
  date strings. Direct Python model construction may also use aware datetime/date
  objects. Do not rely on Pydantic's default coercions to enforce the JSON format.
- Treat timestamps as instants. Normalize to UTC before sorting, comparisons,
  subtraction, window merging, and interval checks. Convert to the trip timezone
  only to derive calendar bounds or display local times.
- Timestamp offsets need not match the trip timezone; `14:00Z` and `09:00-05:00`
  describe the same instant. Do not compare their strings or wall-clock portions.
- During a daylight-saving fall-back, explicit offsets distinguish repeated wall
  times. A spring-forward wall time must be resolved by the client into a real
  instant before submission. The backend interprets any accepted offset timestamp
  as an instant; it does not infer or validate the client's intended wall time.
- Use half-open activity intervals `[start, end)`. Adjacent activities do not overlap.
  Midnight crossings are allowed within trip bounds. Zero duration is invalid.
- Compare exact seconds to `minutes * 60`; never round gaps up to whole minutes.
  A 14-minute-59-second gap fails a 15-minute requirement. No implicit travel buffer.

## Rules

Evaluate independent rules to accumulate failures; do not return only the first.

| Violation code | Detection | Activity IDs and explanation |
| --- | --- | --- |
| `INVALID_INTERVAL` | Activity end <= start in UTC | That ID; state that end must be after start |
| `ACTIVITY_OUTSIDE_TRIP` | A positive interval starts before the lower bound or ends after the upper bound | That ID; identify the allowed trip dates/timezone |
| `OVERLAP` | For every pair of positive intervals, `max(starts) < min(ends)` | Both IDs; name the conflicting activities and overlap |
| `INSUFFICIENT_TRAVEL_TIME` | A consecutive leg's available gap is less than the supplied directed duration | Both IDs in itinerary order; include available and required time |
| `BUDGET_EXCEEDED` | Sum of all activity estimates > budget | All activity IDs in lexical order; include total, budget, and overrun in USD |
| `CLOSED_LOCATION` | A positive activity interval is not wholly covered by its known opening windows | That ID; identify the location and unsupported visit interval |

Specific evaluation rules:

1. Check every activity interval. Exclude nonpositive intervals from overlap,
   opening-hour, and trip-bound checks; they already have `INVALID_INTERVAL`.
   Their costs still count. Positive intervals outside trip bounds still participate
   in the other applicable checks, so independent problems are not hidden.
2. Find all overlapping pairs, including nested intervals and nonadjacent pairs in
   sorted order; emit one violation per unordered pair, not per minute of overlap.
3. For travel, require all activity intervals to be positive and the entire schedule
   to be nonoverlapping. Otherwise skip travel evaluation and emit exactly one
   `TRAVEL_CHECK_SKIPPED` warning identifying all activity IDs. A route through an
   overlapping schedule is ambiguous. Do not also emit missing-leg warnings then.
4. When travel is evaluable, sort activities by UTC start, UTC end, then ID, without
   mutating the request. Check each consecutive pair. Same-location gaps need zero
   travel; other pairs need their directed fact. A gap exactly equal to travel time
   passes. A missing fact warns and skips only that leg. Do not consider trip arrival,
   departure, depot legs, or travel costs not represented as activity costs.
5. Count every activity estimate once, including fixed events and invalid intervals.
   Budget equality passes. No tax, currency conversion, or implicit transport cost.
6. Merge overlapping or touching known opening windows in UTC, then require the
   entire visit to fit within one merged window. Starting at opening and ending at
   closing passes. A gap between windows cannot be bridged by one visit.
7. Missing opening records warn once per location with positive-interval activities.
   Skip only that location's opening checks. An explicit empty window list produces
   `CLOSED_LOCATION` for each positive-interval activity there, without a missing-data warning.
8. `fixed` and `priority` do not suppress violations or cause edits. Return failures
   for conflicting fixed events; validation never performs repair.

For this small MVP, an O(n²) all-pairs overlap pass is acceptable and easy to audit.
Optimization and public-service request limits are later work.

## Response contract

HTTP 200 returns `ValidationResult`:

| Field | Type | Meaning |
| --- | --- | --- |
| `is_valid` | boolean | Exactly `len(violations) == 0` |
| `violations` | list of Violation | Known failed constraints |
| `warnings` | list of ValidationWarning | Missing facts or a skipped check |

Each violation/warning has `code`, `activity_ids: list[str]`, and `message: str`.
Use explicit code literals/enums, not arbitrary free-form codes. Warnings use:

- `MISSING_TRAVEL_TIME`: one per missing consecutive directed leg, IDs in itinerary order.
- `MISSING_OPENING_HOURS`: one per missing location record; IDs in lexical order.
- `TRAVEL_CHECK_SKIPPED`: one per temporally invalid schedule; IDs in lexical order.

`is_valid=true` means **no violations of checked constraints**, not complete real-world
verification. A result with warnings is partially checked. Any future UI must display
those warnings alongside validity. `is_valid=false` may also have warnings.

For stable output, sort the result lists by `(code, tuple(activity_ids))` and use
lexical ID order for unordered pairs. Keep chronological order for travel pairs.
Use stable message templates naming activities and giving relevant times/amounts;
do not generate explanations with AI or rely on the current clock. Tests assert
codes/IDs and useful explanation content rather than incidental prose punctuation.

Malformed requests return FastAPI's standard 422 `detail` body. Unknown fields,
duplicate activity IDs, negative costs, reversed trip dates, unsupported currencies,
invalid facts, and missing timezone information are examples. Invalid itinerary
intervals, overlaps, closed visits, and budget failures are semantic results (200).
Unexpected exceptions remain server errors; do not disguise them as validity results.

## Example API exchange (planned)

`POST /validate` with `Content-Type: application/json`:

```json
{
  "trip": {
    "destination": "Chicago",
    "start_date": "2026-11-02",
    "end_date": "2026-11-02",
    "timezone": "America/Chicago",
    "currency": "USD",
    "budget": "60.00",
    "preferences": ["museums"],
    "activities": [
      {
        "id": "interview",
        "name": "Interview",
        "location": {"id": "office", "name": "Downtown office"},
        "start_time": "2026-11-02T09:00:00-06:00",
        "end_time": "2026-11-02T10:00:00-06:00",
        "estimated_cost": "0.00",
        "priority": "high",
        "fixed": true
      },
      {
        "id": "museum-visit",
        "name": "Museum visit",
        "location": {"id": "museum", "name": "Example museum"},
        "start_time": "2026-11-02T10:30:00-06:00",
        "end_time": "2026-11-02T12:00:00-06:00",
        "estimated_cost": "35.00",
        "priority": "medium",
        "fixed": false
      }
    ]
  },
  "travel_times": [
    {"from_location_id": "office", "to_location_id": "museum", "minutes": 20}
  ],
  "opening_hours": [
    {
      "location_id": "office",
      "windows": [
        {"start_time": "2026-11-02T08:00:00-06:00", "end_time": "2026-11-02T18:00:00-06:00"}
      ]
    },
    {
      "location_id": "museum",
      "windows": [
        {"start_time": "2026-11-02T10:00:00-06:00", "end_time": "2026-11-02T17:00:00-06:00"}
      ]
    }
  ]
}
```

Expected HTTP 200 body:

```json
{"is_valid": true, "violations": [], "warnings": []}
```

Change only the museum start to `2026-11-02T10:10:00-06:00`. Expected HTTP 200:

```json
{
  "is_valid": false,
  "violations": [
    {
      "code": "INSUFFICIENT_TRAVEL_TIME",
      "activity_ids": ["interview", "museum-visit"],
      "message": "Interview to Museum visit allows 10 minutes of travel; 20 minutes are required."
    }
  ],
  "warnings": []
}
```

The message is a sample of the intended explanation; code/IDs and timing semantics
are the stable contract. These examples are synthetic and make no claims about real
office or museum hours.
