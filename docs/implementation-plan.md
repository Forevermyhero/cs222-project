# Implementation status and next work

## Implemented in the Flask prototype

| Work | Files / evidence |
| --- | --- |
| Reproducible dependencies | `backend/requirements.in`, hash-pinned `requirements.lock` |
| Request/result contracts | `backend/app/models.py` and model tests |
| Pure validator | `backend/app/validator.py`, including original fixed-event comparison |
| Candidate scheduling | Greedy planner plus optional OpenAI adapter |
| Public-data boundary | Open-Meteo, Nominatim, Overpass and OSRM adapters |
| Opening-window conversion | Conservative supported OSM subset; unsupported data warns |
| HTTP application | Flask factory, `/api/plan`, `/validate`, example and health endpoints |
| Basic frontend | Trip/fixed-event form, modes, schedule, issues, recheck and download |
| Automated verification | Offline tests, coverage/style checks, GitHub Actions configuration |
| Functional checks | Reusable browser and explicit live-provider smoke scripts |

Executed outcomes and external blockers are recorded separately in
[validation-report.md](validation-report.md). A written adapter and passing mocked
test do not establish access to a real service. GitHub Actions is configured, but
its remote run is not claimed until the branch is pushed and the workflow executes.

## Next independently testable tasks

### 1. Exercise live providers in the target environment

Objective: verify no-key services against actual supported destinations.
Files: `services/providers.py`, `scripts/smoke_live.py`, validation report.
Guidance: enable the documented outbound domains; run the opt-in script and inspect
place coordinates, route directions, opening coverage, and failure messages.
Acceptance: real geocoding, attraction lookup, explicit place lookup and route
requests succeed, with unknown facts still labeled unknown.
Test: `python -m scripts.smoke_live --destination Chicago`.
Suggested commit: `test: record verified public provider integration`.

### 2. Improve place selection and user confirmation

Objective: let users confirm ambiguous geocoding and select activities before planning.
Files: provider adapter, frontend form, pipeline, provider and browser tests.
Guidance: retain stable provider IDs/coordinates and attribution; do not add public
Nominatim autocomplete. Keep live rate limits and small bounded requests.
Acceptance: users can resolve ambiguous places without silently changing commitments.
Test: mocked duplicate names, user selection, and original-baseline invariants.
Suggested commit: `feat: confirm resolved places before itinerary generation`.

### 3. Support flexible-activity edits and limited repair

Objective: allow a user to remove/replace a flexible event and revalidate.
Files: frontend, an optional repair service, pure-rule tests.
Guidance: copy the candidate, retain the authoritative baseline, and adjust only
flexible events. Prefer simple local changes and return unsatisfied constraints.
Acceptance: no fixed event's ID, name, location, times or fixed flag is changed.
Test: valid edits, fixed-event rejection, unrepairable fixed/fixed conflict.
Suggested commit: `feat: edit flexible activities with fixed-event protection`.

### 4. Verify a configured AI provider

Objective: validate structured generation with a real configured model.
Files: `services/generation.py`, service tests, validation report.
Guidance: use a securely configured server key and an allowed provider domain;
keep price/place facts authoritative and independent validation mandatory.
Acceptance: real generation returns known places and all original commitments;
invalid output is explained or rejected. Do not label heuristic output as AI.
Test: existing mocked failures plus an explicitly authorized live request.
Suggested commit: `test: verify configured AI candidate generation`.

Persistence, authentication, advanced preferences and global optimization should
remain separate future tasks. No extra worktree is needed in isolated cloud tasks.
Before committing or publishing this baseline, review its full diff and test report.
