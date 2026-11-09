# Itinerary That Holds Up

A UIUC CS222 travel-planning prototype: enter a trip, keep fixed commitments in
place, inspect the sources, and get a schedule with deterministic constraint checks.

**Current version uses no LLM or paid API.** The planner is a small Python
scheduler. Public map-data adapters require no API key; Chicago example mode is
entirely offline. Live requests, cache hits and failures are visible in the research
log. A venue link is a reference, not proof of current hours or ticket availability.

**中文逐文件导读：[代码都在做什么](docs/code-tour.zh-CN.md)**

## Source layout

```text
src/                        # all application source code
  backend/app/
    main.py                 # Flask routes and HTTP errors
    models.py               # request/result contracts
    validator.py            # pure scheduling rules
    time_utils.py           # timezone/DST handling
    streaming.py            # progress stream to the browser
    services/               # data adapters, candidate scheduling and source evidence
  frontend/
    index.html              # page structure
    static/
      app.js                # form and page controller
      api.js                # JSON and streaming HTTP client
      render.js             # safe rendering of schedules, sources and checklists
      style.css             # responsive visual design
tests/                      # offline tests
scripts/                    # opt-in browser/live-provider smoke checks
docs/                       # architecture, contracts, walkthrough and evidence
```

`src` is the conventional abbreviation for source code. Run commands from the
repository root so Python can import `src.backend`; no path modifications are needed.

## Install and run

Python 3.12, from the repository root:

```sh
python3.12 -m venv .venv
. .venv/bin/activate
python -m pip install --require-hashes -r requirements.lock
python -m flask --app src.backend.app.main:create_app run --host 127.0.0.1 --port 8000
```

On Windows, activate with `.venv\Scripts\activate` instead of the `source` command.
The current cloud instance already has `/workspace/.venvs/cs222-project`; activate
that environment when continuing here. Cloud tasks are isolated; use the existing
checkout without creating a second Git worktree.

The page loads the Chicago example. Click **Build & check my itinerary**. The result
contains four flexible visits around a fixed interview. Open **Research log** to
see the steps and source records, and **Before you go** for unverified preparation
suggestions. The download contains the schedule, original commitments, facts,
research log and links. Demo hours, prices, meeting coordinates and travel times
are synthetic and visibly labeled; no site is contacted in this mode.

[Desktop screenshot](docs/screenshots/desktop.png) ·
[Research log screenshot](docs/screenshots/research.png) ·
[Mobile screenshot](docs/screenshots/mobile.png)

## Free public-data mode

Select **Public map services · live lookup** for real HTTP requests to:

| Service | Use |
| --- | --- |
| Open-Meteo geocoding | Resolve a city and its timezone |
| Nominatim / OpenStreetMap | Resolve explicitly requested places and fixed-event addresses |
| Overpass / OpenStreetMap | Retrieve a small nearby attraction list and opening/website tags |
| OSRM | Directed estimated **driving** times, without live traffic |

Outbound destinations:

- `geocoding-api.open-meteo.com`
- `nominatim.openstreetmap.org`
- `overpass-api.de`
- `router.project-osrm.org`

These are public services with limited capacity, not guaranteed production APIs.
The client caches public results for 15 minutes and serializes Nominatim requests
at no more than one per second. There is no autocomplete or bulk geocoding.

This cloud's applied allowlist initially blocked the destinations. The required
domains were saved in environment settings as a draft; saving is not application
or publication. See [the validation record](docs/validation-report.md) for observed
results. A failed live lookup is displayed as failed; it never becomes demo data.

Opening tags are not always available or parseable. Unknown hours/routes stay
unverified. A record's venue website is shown as **not checked here**: the prototype
does not scrape arbitrary pages, check inventory, buy tickets or make reservations.

## HTTP endpoints

| Endpoint | Responsibility |
| --- | --- |
| `GET /` | Serve the interface |
| `GET /api/health` | Local capability flags; `llm_connected=false`, no remote calls |
| `GET /api/example` | Offline starter input |
| `POST /api/plan` | One complete JSON planning result |
| `POST /api/plan/stream` | Actual progress events, then one result/error, as newline-delimited JSON |
| `POST /validate` | Validate an existing candidate against its original commitments and supplied facts |

`is_valid=true` means no known constraint failed. Missing-data warnings mean partial
coverage. The original fixed events are stored separately from the candidate, so
moved or deleted commitments can be detected. Budget checking is optional and only
uses supplied estimates; unknown prices are not treated as free.

```sh
curl --fail-with-body -H 'Content-Type: application/json' \
  --data-binary @examples/plan-demo.json http://127.0.0.1:8000/api/plan
curl --fail-with-body -H 'Content-Type: application/json' \
  --data-binary @examples/validate-valid.json http://127.0.0.1:8000/validate
```

## Tests

```sh
python -m flake8 src tests scripts
python -m pytest --cov=src/backend/app --cov-report=term-missing --cov-fail-under=90
```

The default suite forbids real HTTP and uses injected provider responses. It requires
no API keys, database or running server. To explicitly contact real map services:

```sh
python -m scripts.smoke_live --destination Chicago
```

Optional browser tooling is separate from application dependencies. With Playwright
and Chromium available and the Flask server running:

```sh
python -m scripts.smoke_browser --chromium /usr/bin/chromium
```

Browser outputs go into ignored `test-results/`. GitHub Actions installs the hash-locked
dependencies and runs style/coverage checks. No remote CI outcome is claimed without
observing its run.

## Further reading and limits

- [逐个文件的中文说明](docs/code-tour.zh-CN.md)
- [Check-In #4 demonstration notes](docs/checkin4-demo.md)
- [Architecture](docs/architecture.md), [API contract](docs/mvp-spec.md)
- [Next tasks](docs/implementation-plan.md), [test plan](docs/test-plan.md)
- [Executed validation and external blockers](docs/validation-report.md)

LLM integration remains a future proposal step. It can call the same lookup tools,
return structured candidates, and still use the independent validator. This version
has no model credentials, model API calls or autonomous web crawler. Persistence,
automatic repair, walking/transit routing, bookings and global optimization are also
outside this prototype.

For intentional dependency updates, edit `requirements.in`, regenerate with the
separate pip-tools development tool, and review the resulting pins/hashes:

```sh
python -m piptools compile --generate-hashes --no-emit-index-url \
  --no-emit-trusted-host --output-file requirements.lock requirements.in
```

Develop on feature branches and use teammate review before merging into `main`.
