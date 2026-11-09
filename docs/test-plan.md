# Test plan and verification boundary

## Offline suite

Run `python -m pytest --cov=backend/app --cov-report=term-missing --cov-fail-under=90`
from the repository root. An autouse fixture rejects accidental real HTTP requests.
Tests use fixed dates and exact decimal amounts. No API keys, database or running
server are needed. Style is checked with `python -m flake8 backend scripts`.

| Area | Existing cases |
| --- | --- |
| Models | Required fields, blank values, strict flags/minutes, timezone/offset errors, invalid dates, cost precision, duplicate IDs/fact keys, missing baseline, unknown locations, paired coordinates |
| Pure rules | Valid itinerary; invalid intervals; trip bounds; every overlap pair; directed travel gaps; optional budget; closed locations; missing-data warnings |
| Fixed events | Original event preserved; moved, deleted, replaced/renamed, changed location/flag; unexpected candidate fixed event |
| Boundaries | Adjacent intervals; exact travel/budget/opening equality; one-second shortfall; touching opening windows; opening gaps; midnight; UTC-equivalent offsets; DST |
| Invariants | No request mutation, original order retained, deterministic repeated/permuted results, accumulation of independent failures |
| Provider adapters | Request headers/timeouts; cache expiry; Nominatim throttling; malformed/missing data; directed OSRM rounding; unknown routes; service timeouts |
| Opening parser | Supported weekday/time/overnight/closed expressions; unsupported holidays and invalid clocks remain unknown |
| Pipeline | Offline demo, retained baseline, unscheduled visits, mocked live data, missing route/hour coverage, failed services, explicit modes |
| Optional AI | Missing key, malformed JSON, candidate parsing, independent detection of changed fixed time, ungrounded prices discarded |
| Flask | HTML/assets, security headers, request/result parity, 200 semantic failures, 422 shape errors, 400/413/415 HTTP errors, 503 provider failures, key-free health output |

Candidate fixed-event comparison must use a separate original baseline. Merely
checking that the validator does not mutate its input is not enough. Test AI
responses with deliberately changed original times even when the returned schedule
would otherwise be nonoverlapping.

## Real HTTP and browser checks

Start Flask using the README command and submit both example files. Inspect result
bodies, not only the listening port. The sample plan must preserve the interview,
produce the expected visits, and match an independent `/validate` call. Editing a
flexible interval to overlap the interview must report an overlap.

The optional `scripts.smoke_browser` checks desktop and mobile form flows,
revalidation, itinerary download, visible synthetic-data labeling, safe rendering
of user text, server-side error display, event add/remove, and absence of page errors.
It saves screenshots and the exported itinerary under an ignored output path.

## Real external-service checks

`scripts.smoke_live` deliberately contacts the public map APIs. Its failures are
not hidden by demo fallback. It exercises geocoding, attraction lookup, one explicit
Nominatim place query, directed driving routes and the planning pipeline. Unknown
opening information may legitimately leave coverage incomplete.

A live AI call is separate and requires a configured key/model and outbound access.
Mocked OpenAI tests verify our contract handling, not the behavior of a real model.
No live API, browser or remote CI result should be described as passed unless that
check actually executed and completed. See the recorded validation report.
