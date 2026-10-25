# Offline test plan

## Status and execution strategy

This is a specification for future pytest tests; no tests or test results exist yet.
Use fresh fixture factories under `backend/tests/conftest.py`, fixed dates, exact
decimal amounts, and supplied durations/windows. No test may call OpenAI, Google,
a geocoder, or a live database. Dependency installation may need network access;
test execution must not. TestClient uses the in-process app, not a running external
server. A separate local HTTP smoke test is required only after the API exists.

For a successfully parsed request, assert exact violation and warning code/ID sets,
`is_valid == (not violations)`, deterministic ordering, and useful explanation facts.
Do not assert only a boolean or a status code. Model-error tests assert Pydantic
`ValidationError`; their API equivalents assert HTTP 422 with a `detail` body.

## Canonical fixture

Use the full request in [mvp-spec.md](mvp-spec.md), with these synthetic facts:

| Item | Value |
| --- | --- |
| Trip | Chicago; November 2, 2026 only; `America/Chicago`; USD budget `60.00` |
| `interview` | office; 09:00–10:00, offset `-06:00`; cost `0.00`; high priority; fixed |
| `museum-visit` | museum; 10:30–12:00, offset `-06:00`; cost `35.00`; medium priority; flexible |
| Travel | office→museum = 20 minutes |
| Office hours | 08:00–18:00, same date/offset |
| Museum hours | 10:00–17:00, same date/offset |

Every mutation below begins with a fresh canonical request unless explicitly stated.
Do not reuse a mutable model or modify a shared dictionary between tests. Parse
modified input through Pydantic instead of using unchecked model-copy updates for
tests that are meant to exercise request validation.

## Required seven scenarios

| Suggested test | Input change | Expected result from pure validator |
| --- | --- | --- |
| `test_valid_itinerary` | None | `is_valid=true`; no violations or warnings |
| `test_overlap` | Interview ends 10:45 | `is_valid=false`; one `OVERLAP` for `interview`, `museum-visit`; one `TRAVEL_CHECK_SKIPPED` warning; explanation names both events |
| `test_insufficient_travel` | Museum begins 10:10 | One `INSUFFICIENT_TRAVEL_TIME` for the ordered pair; message gives 10 available and 20 required minutes; no warnings |
| `test_budget_exceeded` | Budget `30.00` | One `BUDGET_EXCEEDED` listing both IDs; message includes total `35.00`, budget `30.00`, excess `5.00`; no warnings |
| `test_closed_location` | Museum opening starts 11:00 | One `CLOSED_LOCATION` for `museum-visit`, identifying the unsupported visit; no warnings |
| `test_invalid_interval` | Museum starts 12:00 and ends 11:00 | One `INVALID_INTERVAL` for `museum-visit`; one `TRAVEL_CHECK_SKIPPED`; no overlap/opening/bounds violation for that activity |
| `test_fixed_event_preserved` | First validate the canonical request; then separately validate the overlapping version | Before/after entire request equality in both calls; fixed interview ID, location, times, flag intact; overlap still reported in second result; no repair or movement |

Once the API exists, parameterize these request variants through `POST /validate`:
each has HTTP 200 with a body identical to the serialized pure result. Fixed-event
immutability is primarily a pure-function test; the API must never return a silently
revised trip. No future repair implementation is required to pass this scenario.

## Required boundaries and missing-data cases

| Area | Input / setup | Expected behavior |
| --- | --- | --- |
| Adjacent, same place | Museum at office starting exactly 10:00; remove now-unused museum facts; provide office hours | No overlap or travel violation; no warnings |
| Adjacent, different places | Museum starts 10:00; keep 20-minute fact | Travel violation only; zero gap does not overlap |
| Exact travel time | Museum starts 10:20 | Passes without warnings |
| Seconds matter | Museum starts 10:19:59 | Travel violation; gap is 19m59s, not 20m |
| Explicit zero travel | Museum starts 10:00; office→museum = 0 | Passes without overlap or travel violation |
| Missing travel data | Remove all travel facts | `is_valid=true`, no violations, one `MISSING_TRAVEL_TIME` warning with both IDs |
| Directed travel | Supply only museum→office = 20 | Same missing office→museum warning; reverse is not reused |
| Missing opening data | Remove museum opening record | `is_valid=true`; one `MISSING_OPENING_HOURS` for `museum-visit` |
| All optional facts omitted | Omit both request fact lists | No violations; one missing-travel warning and two missing-opening warnings; not fully verified |
| Explicitly closed | Museum record has `windows=[]` | `CLOSED_LOCATION` for museum; no missing-opening warning |
| Opening boundary equality | Museum visit equals known window 10:30–12:00 | Passes |
| Opening overrun | Museum closes at 11:59:59 | `CLOSED_LOCATION` |
| Touching opening windows | Museum windows 10:00–11:00 and 11:00–17:00 | Merged coverage permits 10:30–12:00 visit |
| Opening gap | Museum windows 10:00–11:00 and 11:30–17:00 | Visit spans closed gap; `CLOSED_LOCATION` |
| Exact budget | Budget `35.00` | Passes |
| Decimal precision | Costs `0.10` and `0.20`, budget `0.30` | Passes using Decimal equality |
| Empty itinerary | `activities=[]`, budget `0.00`, no fact records | Valid, no warnings |
| Zero-duration activity | Museum start equals end | `INVALID_INTERVAL`; one skipped-travel warning |
| Lower trip bound | Replace activities with one visit starting Nov 2 at 00:00, ending 01:00; matching hours, no travel facts | Passes |
| Upper trip bound | One visit Nov 2 at 23:00 to Nov 3 at 00:00; matching hours | Passes; end at exclusive upper bound is allowed |
| Outside trip | Same upper-bound visit ends Nov 3 at 00:00:01; matching hours | `ACTIVITY_OUTSIDE_TRIP` only |
| Midnight crossing | Trip Nov 2–3; visit Nov 2 23:30 to Nov 3 00:30; matching hours | Passes |
| Equivalent offsets | Replace every timestamp in the canonical request with its equivalent UTC representation | Same result as canonical; no wall-clock comparison |
| DST fall-back | Nov 1, 2026 trip in Chicago; single visit `01:15-05:00` to `01:45-06:00`, matching opening window | Valid 90-minute elapsed interval |
| DST spring-forward | Mar 8, 2026 trip in Chicago; visit `01:30-06:00` to `03:30-05:00`, matching window | Valid 60-minute elapsed interval |
| Offset interpretation | Single Chicago visit `2026-03-08T02:30:00-06:00` to `04:00:00-05:00`, trip Mar 8, matching window | Interpreted as 08:30Z–09:00Z (03:30–04:00 local), a valid 30-minute interval; no inference of intended nonexistent wall time |
| Nested overlaps | One place, A 09:00–12:00, B 10:00–11:00, C 10:30–11:30; sufficient budget/hours | Exactly A/B, A/C, B/C overlap violations; one skipped-travel warning |
| Shared missing hours | Two nonoverlapping activities at same location without opening record | One missing-opening warning listing both IDs; no missing-travel warning |
| Input order | Reverse canonical activity list before parsing | Same result; caller order remains reversed after validation |
| Repeated evaluation | Validate same request twice | Identical results; request and fact data unchanged |
| Cost of invalid event | Canonical request with budget `30.00` and reversed museum interval | `BUDGET_EXCEEDED` and `INVALID_INTERVAL`; one skipped-travel warning |

For custom single-activity temporal tests, provide one authoritative matching opening
record and no travel facts. This isolates time behavior without accidental missing-data
warnings or invalid references. For all changed locations, remove facts that no longer
refer to a location in the trip; model validation rejects unused/unknown location IDs.

## Required malformed-input cases

Implement these as parameterized model tests, then reuse representative inputs in
API tests. All must fail parsing / return 422 rather than a semantic validity result:

- Missing required Trip or Activity fields; misspelled or extra request fields.
- Blank destination, activity ID/name, location ID/name, or preference item.
- Duplicate activity IDs after trimming; duplicated directed travel pair or opening location.
- Trip end date before start; invalid date; end date `9999-12-31` (no next-day bound).
- Invalid IANA timezone; naive activity timestamps or naive opening-window timestamps.
- Numeric epoch timestamps and non-string JSON trip dates, even when Pydantic could coerce them.
- Negative budget/cost; nonfinite money; more than two decimal places; currency other than USD.
- Invalid priority; nonboolean `fixed`; negative, fractional, or boolean travel minutes.
- Fact references to an unknown location; explicit same-location travel fact.
- Zero/reversed opening window. Contrast this with the accepted Activity interval
  input that the semantic validator must report as `INVALID_INTERVAL`.

Also test defaults: two independently parsed models do not share preferences/fact
lists; omitted priority/fixed/currency resolve to `medium`/`false`/`USD`.

## Cross-rule accumulation and explanations

Take the canonical fixture, end the interview at 10:45, lower the budget to `30.00`,
and set museum windows to `[]`. Expect exactly `OVERLAP`, `BUDGET_EXCEEDED`, and
`CLOSED_LOCATION`, plus one `TRAVEL_CHECK_SKIPPED` warning. Verify all affected IDs
and that the messages give conflicting event names, monetary overrun, and closed
location respectively. No failure should hide an independent failure.

Add a result-order check using multiple violations and warnings. Sort by code and
activity-ID tuple as specified; travel pairs retain itinerary order and overlap
pairs use lexical ID order. Avoid random UUIDs or set iteration in expected outputs.

## API and milestone verification

After task 6 adds the endpoint:

1. Use FastAPI TestClient with the valid example; require 200 and the exact valid body.
2. Submit each required semantic-failure variant; require 200, expected codes/IDs,
   and parity with the pure function result.
3. Submit malformed cases such as naive time, duplicate IDs, and negative cost;
   require 422 with relevant field/error details.
4. Submit a missing-fact request; require 200 with `is_valid=true` and visible warnings.
5. Run `python -m pytest backend/tests` from the repository root. Record actual
   collected/passed/failed/skipped counts; a zero-test run is not completion.
6. Start Uvicorn and make the representative local POST described in the implementation
   plan. Inspect the response body, then stop the server.

No performance suite, frontend test, live API test, database migration test, or AI
quality evaluation is required for this milestone. Those become separate work only
when their components exist. Do not mark any check as passed until it has run.
