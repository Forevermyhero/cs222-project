# Itinerary That Holds Up

A UIUC CS222 travel-planning prototype built around commitments that must stay fixed.
Users enter a city, dates, preferences, desired places, and fixed events. A candidate
planner proposes a schedule; an independent Python validator explains whether it
fits the supplied constraints.

## What is implemented

- A Flask backend and responsive HTML/CSS/JavaScript interface.
- Pydantic contracts for trips, activities, authoritative original fixed events,
  directed travel estimates, opening windows, and validation results.
- Deterministic overlap, travel-time, opening-hour, trip-bound, and fixed-event checks.
- Optional budget checks using supplied estimates; unknown prices remain unknown.
- A no-key rule-based planner and a completely offline Chicago demonstration.
- Adapters for Open-Meteo geocoding, OpenStreetMap via Nominatim/Overpass, and OSRM driving times.
- An optional OpenAI candidate generator, with schema checks and independent revalidation.
- Offline regression tests, opt-in HTTP/browser/live-service smoke checks, and GitHub Actions.

This follows the final proposal's Flask/basic-JavaScript direction. The original
FastAPI/React-only design has been replaced. Persistence, automatic repair, transit
routing, bookings, and global schedule optimization remain future work.

## Run locally

Use Python 3.12. From the repository root:

```sh
python3.12 -m venv .venv
. .venv/bin/activate
python -m pip install --require-hashes -r backend/requirements.lock
python -m flask --app backend.app.main:create_app run --host 127.0.0.1 --port 8000
```

Open the locally running application in your browser. The page loads the Chicago
example; select **Build & check my itinerary**. It schedules four flexible visits
around the fixed interview. Demo hours, prices, office coordinates, and 20-minute
travel estimates are synthetic fixtures, explicitly labeled in the result.

The current cloud instance uses `/workspace/.venvs/cs222-project` instead of `.venv`.
Activate that existing environment when continuing work here. Each cloud task is
already isolated; use the existing checkout without creating another Git worktree.

## Modes and external services

| Mode | Credentials | Behavior |
| --- | --- | --- |
| Example data + rule-based planner | None | Offline, deterministic, synthetic Chicago facts |
| Live public data + rule-based planner | None | Fetch city, places/opening tags, and estimated driving times |
| OpenAI planner | Server-side key | Generate structured candidates using supplied places, then validate |

Live services require outbound access to:

- `geocoding-api.open-meteo.com`
- `nominatim.openstreetmap.org`
- `overpass-api.de`
- `router.project-osrm.org`

These public endpoints have limited capacity and no availability guarantee. Queries
are cached for 15 minutes. Nominatim calls are serialized at no more than one per
second; there is no autocomplete or bulk geocoding. Attribution is shown in the UI.

The managed cloud's current network policy initially blocked these domains. Domain
additions were saved as an environment draft; a saved draft does not establish live
connectivity. See [validation evidence](docs/validation-report.md) for observed outcomes.

For optional AI planning, configure `PLANNER_API_KEY` securely in the server
process and optionally set `PLANNER_MODEL` (default `gpt-4.1-mini`). Permit
`api.openai.com` in the server's outbound policy. `.env.example` documents names;
the app does not automatically load `.env` files. Keys never belong in the frontend,
repository, screenshots, or report output. OpenAI is not advertised as a free service.
Without a configured key, the OpenAI UI option is disabled; explicit API attempts
return a clear 503 instead of silently switching planners.

## Tests and functional checks

With the environment activated, from the repository root:

```sh
python -m flake8 backend scripts
python -m pytest --cov=backend/app --cov-report=term-missing --cov-fail-under=90
```

The pytest suite forbids real HTTP requests and uses injected provider responses.
It does not require API keys, public endpoints, a database, or a running server.

To deliberately test the real no-key providers:

```sh
python -m scripts.smoke_live --destination Chicago
```

This makes real public requests and exits nonzero when a required service fails.
Missing or unsupported opening data is reported as incomplete coverage, not guessed.
It is deliberately separate from CI. OSRM estimates are for **driving**, without
live traffic; this prototype does not claim walking or transit estimates.

Optional browser checks need Playwright and an installed Chromium, separately from
application dependencies. With the Flask server running and that tooling available:

```sh
python -m scripts.smoke_browser --chromium /usr/bin/chromium
```

The script checks desktop/mobile planning, fixed-event display, revalidation,
download, error messages, and safe rendering of user text. Outputs are ignored under
`test-results/`. [Recorded checks](docs/validation-report.md) distinguish executed
checks, mocked integrations, and blocked live operations.

## API examples

```sh
curl --fail-with-body -H 'Content-Type: application/json' \
  --data-binary @examples/plan-demo.json http://127.0.0.1:8000/api/plan
curl --fail-with-body -H 'Content-Type: application/json' \
  --data-binary @examples/validate-valid.json http://127.0.0.1:8000/validate
```

`POST /api/plan` returns the candidate trip, its authoritative fixed-event baseline,
facts, validation, source mode, planner name, notes and attribution. Its `request`
field can be sent directly to `POST /validate` after editing flexible activities.
A positive `is_valid` means no failed **known** constraints. Warnings mean some
checks remain unverified; the UI presents this as **Partially checked**.

## Development references

- [Architecture and responsibilities](docs/architecture.md)
- [Implemented API and rule contract](docs/mvp-spec.md)
- [Completed work and next tasks](docs/implementation-plan.md)
- [Test strategy](docs/test-plan.md)
- [Validation evidence and limitations](docs/validation-report.md)

Update direct dependency bounds in `backend/requirements.in` intentionally, then
regenerate the lock with pip-tools and review the result:

```sh
python -m piptools compile --generate-hashes --no-emit-index-url \
  --no-emit-trusted-host --output-file backend/requirements.lock backend/requirements.in
```

pip-tools is a separate development tool, not a runtime dependency. Major changes
should use a feature branch and PR, with another teammate reviewing before merge.
