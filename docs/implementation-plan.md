# Implementation plan

## Completed versus planned

Completed in this documentation change: inspected the repository/history, confirmed
the remote `main` matches initial commit `d26d7e9`, created a documentation feature
branch, and wrote the README, architecture, MVP specification, implementation plan,
and test plan. No application files, dependency files, tests, or CI have been added.

All coding tasks below are **planned**. Work in order: models, pure rules, expanded
unit tests, then FastAPI. Each task adds its own focused tests; do not defer every
check until the dedicated test task. Suggested commit messages are for the student;
this documentation run does not commit, push, merge, or open a PR.

Commands below assume repository-root working directory, Python 3.12, and the virtual
environment activated as described in the README. Use the existing isolated cloud
checkout; no additional Git worktree is necessary. Review `git status` before edits
and preserve any teammate changes. Later changes should use separate feature branches.

## Task 1 — Define and test the Pydantic contract

**Objective:** parse offline trip requests and represent stable results without
implementing scheduling rules or starting a server.

**Files involved (create):** `backend/__init__.py`, `backend/app/__init__.py`,
`backend/app/models.py`, `backend/tests/__init__.py`, `backend/tests/test_models.py`,
`backend/requirements.in`, `backend/requirements.lock`.

**Implementation guidance:**

1. Confirm a clean starting point with `git status --short --branch`. Create or
   switch to a coding branch based on the documentation once it is available in Git.
   Leave this documentation branch's uncommitted files intact; do not discard them.
2. Create the package directories and empty `__init__.py` files listed above. Do
   not create `main.py`, a frontend, or database tables yet.
3. In `requirements.in`, declare `pydantic>=2,<3` and `pytest>=8,<9`. Add the small
   `tzdata` package for portable IANA timezone availability. Use pip-tools as a
   development lock-generation tool, installed in the external virtual environment;
   it need not be an application dependency. Generate and review a fully pinned
   `requirements.lock`, then install from it. Do not hand-invent transitive pins.
4. Implement Location, Activity, Trip, OpeningWindow, OpeningHours, TravelTime,
   ValidationRequest, Violation, ValidationWarning, and ValidationResult using the
   field definitions in [mvp-spec.md](mvp-spec.md). Define code types as literals or
   enums. Use Pydantic `AwareDatetime`, constrained `Decimal`, strict booleans/integers,
   and `Field(default_factory=list)` as appropriate.
   Enforce ISO string timestamps at the JSON boundary; `AwareDatetime` alone also
   accepts numeric epochs, which are outside this contract. Python datetime objects
   are acceptable in direct model tests if they are aware. Use the same policy for
   opening windows, and use ISO date strings at the JSON boundary for trip dates.
5. Keep validation layers separate: field/cross-field input checks belong in models;
   activity interval ordering belongs in the pure validator. Validate trip date order,
   timezone existence, unique activity IDs, unique fact keys, known fact locations,
   positive fact windows, and forbidden self-pair travel facts in model validators.
6. Write model tests for accepted sample data and rejected malformed input. Verify
   a zero/reversed activity interval still parses, so the later validator can explain it.

Intended dependency commands after authoring `requirements.in`:

```sh
python3.12 -m venv /workspace/.venvs/cs222-project
. /workspace/.venvs/cs222-project/bin/activate
python -m pip install pip-tools
python -m piptools compile --output-file backend/requirements.lock backend/requirements.in
python -m pip install -r backend/requirements.lock
python -m pytest backend/tests/test_models.py
```

Lock generation needs registry access; the installed test suite itself must not
need network access. Review the generated pins before committing them. Pinning the
lock-generation tool can be added to development tooling if the team needs byte-for-byte
lock regeneration; it is not a runtime framework.

**Acceptance criteria:** the example request parses; all defaults are independent;
malformed inputs raise Pydantic `ValidationError`; nonpositive activity intervals
parse; decimal arithmetic remains exact; the package imports from repository root.

**How to test:** `python -m pytest backend/tests/test_models.py`; include the model
cases in the test plan. No FastAPI or HTTPX dependency is needed at this stage.

**Suggested commit:** `feat: define itinerary validation models`

## Task 2 — Add interval, trip-bound, and overlap checks

**Objective:** establish the pure validator entry point and temporal semantics.

**Files involved:** create `backend/app/validator.py`,
`backend/tests/test_validator.py`, and `backend/tests/conftest.py`.

**Implementation guidance / pseudocode:**

```text
validate_itinerary(request):
    make local indexes and result lists; do not edit request
    convert activity endpoints to UTC
    report INVALID_INTERVAL for nonpositive intervals
    derive the trip's local midnight bounds, then convert bounds to UTC
    report ACTIVITY_OUTSIDE_TRIP for positive intervals outside bounds
    for every unordered pair of positive intervals:
        if max(start_a, start_b) < min(end_a, end_b): report OVERLAP
    finalize deterministic result ordering; is_valid = no violations
```

This task's function is intentionally incomplete until tasks 3 and 4. Mark that
status in its docstring and do not expose it as a completed validation API. Write
the shared fixture factory from the spec's synthetic example; return a fresh object
per call. Python datetimes with the same ZoneInfo can behave unexpectedly across DST
when subtracted directly; normalize to UTC first.

**Acceptance criteria:** adjacent intervals pass, nested/nonadjacent overlaps are
found once per pair, invalid intervals are excluded from pair comparisons, and
cross-midnight/DST comparisons follow the spec. Input order and fields remain intact.

**How to test:** `python -m pytest backend/tests/test_validator.py -k 'interval or overlap or trip_bound or timezone'`;
ensure the selected tests actually execute. Include equality and out-of-trip bounds.

**Suggested commit:** `feat: validate activity intervals and overlaps`

## Task 3 — Check travel gaps and budget

**Objective:** evaluate consecutive transfers and exact monetary totals.

**Files involved:** `backend/app/validator.py`, `backend/tests/test_validator.py`.

**Implementation guidance / pseudocode:**

```text
total = sum(all estimated_cost values, starting with Decimal("0.00"))
if total > budget: report BUDGET_EXCEEDED
if any interval is nonpositive or any overlap exists:
    report one TRAVEL_CHECK_SKIPPED warning
else:
    sort a copy by (UTC start, UTC end, id)
    for each consecutive pair:
        same location -> required duration is zero
        missing directed fact -> warn MISSING_TRAVEL_TIME and continue
        otherwise compare exact gap with timedelta(minutes=fact.minutes)
        report INSUFFICIENT_TRAVEL_TIME when gap is smaller
```

Keep directed lookup separate from display names. Do not infer reverse durations,
round seconds, add estimated travel costs, or discard costs from invalid activities.

**Acceptance criteria:** exact-gap and exact-budget equality pass; one second too
little travel fails; missing facts warn; A→B does not satisfy B→A; fixed events count
normally; no travel result is guessed for overlapping schedules.

**How to test:** `python -m pytest backend/tests/test_validator.py -k 'travel or budget'`.
Also rerun the complete validator module after adding these rules because existing
temporal-failure cases now acquire a skipped-travel warning.

**Suggested commit:** `feat: validate travel gaps and trip budget`

## Task 4 — Check opening windows and complete the pure function

**Objective:** finish the first MVP rule set and explain data coverage honestly.

**Files involved:** `backend/app/validator.py`, `backend/tests/test_validator.py`.

**Implementation guidance:** index opening records by location; sort and merge
touching/overlapping windows in UTC using local copies. For each positive activity,
require containment in a merged window. Missing record: one warning per location.
Explicit empty windows: a closure violation for each visit. Nonpositive activities
are excluded from opening checks. Keep names/times/amounts in deterministic messages.
Finalize every response by sorting lists using the contract and computing `is_valid`
from violations only. Remove the function's incomplete-status note once all rules exist.
Normalize unordered ID pairs before building their messages, too, so input list
permutations cannot change explanation order. Format monetary amounts to two decimal
places with the currency, without introducing float arithmetic.

**Acceptance criteria:** exact opening/closing boundaries pass; a one-second overrun
fails; an opening gap cannot contain a visit; unknown hours warn; empty hours mean
closed; all independent failures accumulate. No provider SDK or network call exists.

**How to test:** `python -m pytest backend/tests/test_validator.py`; assert both
violations and warnings, including the fully valid spec example with neither.

**Suggested commit:** `feat: validate supplied opening hours`

## Task 5 — Complete offline regression and boundary tests

**Objective:** demonstrate the pure validator is correct across rules and preserves
fixed commitments, with reproducible failures when a rule is broken.

**Files involved:** `backend/tests/conftest.py`, `backend/tests/test_models.py`,
`backend/tests/test_validator.py`.

**Implementation guidance:** implement every required model and pure-function case
in [test-plan.md](test-plan.md); leave HTTP cases for task 6.
Use parameterized tests for boundaries; construct independent inputs per test.
Compare a deep copy of the complete request before/after validation, including fixed
event fields and fact lists. Add a permutation test: reversing the input activity
list must preserve the output and must not reorder the original list. Check all
overlap pairs for a three-event nested schedule and a combined independent-failure case.

**Acceptance criteria:** the required seven scenarios, all boundary/model cases,
and combined-rule case pass. Assertions cover exact code/ID sets, warnings, `is_valid`,
and useful explanation facts. No live network, clock, credentials, or DB is used.
There are no skipped core cases or zero-test selections hidden as passing results.

**How to test:** `python -m pytest backend/tests/test_models.py backend/tests/test_validator.py`.
Inspect the pytest summary and confirm collected cases ran; coverage tooling is optional.

**Suggested commit:** `test: cover itinerary validator boundaries and invariants`

## Task 6 — Expose the FastAPI endpoint

**Objective:** make the tested pure behavior available at `POST /validate`.

**Files involved:** create `backend/app/main.py` and `backend/tests/test_api.py`;
update `backend/requirements.in`, regenerate `backend/requirements.lock`.

**Implementation guidance:** add FastAPI with a bounded major version (`fastapi>=0.115,<1`),
Uvicorn (`uvicorn>=0.30,<1`) for local serving, and HTTPX (`httpx>=0.27,<1`) for tests.
Resolve their compatible versions into the lockfile; do not require any provider SDK.
Create `app = FastAPI()`. Declare a POST route with `ValidationRequest` input and
`ValidationResult` response model; its body should simply call `validate_itinerary`.
Use `TestClient` as a context manager. Let FastAPI return standard 422 errors; do
not catch all exceptions or move business rules into the route.

**Acceptance criteria:** the sample passes with HTTP 200; semantic failures return
200 with `is_valid=false`; malformed input returns 422; API and pure results agree;
an actual local server responds to a representative validation request. All tests pass.

**How to test:** regenerate/install the lock using task 1's commands, then run:

```sh
python -m pytest backend/tests
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

In another terminal, submit the spec example with a local HTTP client. If you save
the JSON request as `/tmp/itinerary-valid.json`, use:

```sh
curl --fail-with-body --silent --show-error \
  -H 'Content-Type: application/json' \
  --data-binary @/tmp/itinerary-valid.json \
  http://127.0.0.1:8000/validate
```

Assert the body equals the valid result in the spec; an open port alone is not a
smoke test. Stop the server when done. Local requests need no external credentials.
This command is an internal check, not a hosted-preview link.

**Suggested commit:** `feat: expose itinerary validation endpoint`

## Task 7 — Verify clean installation and update the handoff

**Objective:** make the implemented milestone reproducible for another teammate.

**Files involved:** `README.md` and these docs as needed to reflect actual completion;
dependency files only if clean-install verification reveals a setup issue.

**Implementation guidance:** create a fresh external virtual environment, install
from `backend/requirements.lock`, and run the entire suite plus the functional request.
Record actual commands and results. Replace planned-status text only for files and
behaviors now verified. Keep AI, storage, UI, and repair marked as later work.

**Acceptance criteria:** a teammate can install, run tests, start the API, and submit
the example using only documented commands; no credentials or undeclared services
are required. Required tests are executed and their failures explained or fixed.

**How to test:** repeat task 6's full-suite and local request from the fresh environment.

**Suggested commit:** `docs: document the working validator milestone`

## First coding action

Begin with **task 1 only**: create the dependency/package files, define Location and
Activity, and test one valid activity plus naive timestamps, negative cost, and a
parseable reversed interval. Then add Trip and the request/result models and their
cross-field tests. Do not start by integrating OpenAI or building the frontend.
