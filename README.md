# Itinerary That Holds Up

A UIUC CS222 Software Design Lab team project: an AI-assisted travel planner that
builds realistic itineraries around fixed commitments such as interviews, flights,
meetings, and reservations.

The intended system separates **generating suggestions** from **checking whether a
schedule works**. AI can propose activities; deterministic Python rules will explain
overlaps, travel-time problems, budget overruns, and visits to closed locations.
Future repair must preserve fixed commitments.

## Current status

Repository inspection found one commit, `d26d7e9` (`Initial commit`), containing only
this README. The remote `main` matched that commit at inspection. No application,
dependency manifest, tests, CI workflow, or development scripts existed.

This documentation milestone adds the architecture, MVP contract, implementation
tasks, and test plan. **Application implementation has not started.** There is no
server or frontend to run yet. No teammate implementation is assumed.

## First development milestone

Implement an offline backend that accepts a structured trip at `POST /validate`
and returns deterministic violations and data-coverage warnings. Completion means:

- Pydantic models enforce the documented request and response shapes.
- A pure Python validator checks intervals, trip bounds, overlaps, travel time,
  budget, and supplied opening hours without changing the input.
- Pytest covers valid, invalid, boundary, and missing-data cases.
- A thin FastAPI endpoint exposes the same behavior and has API tests.

No API keys, database, React app, AI generation, live place lookup, authentication,
or automatic repair are required for this milestone.

## Documentation

| Document | Purpose |
| --- | --- |
| [Architecture](docs/architecture.md) | Boundaries, component responsibilities, and planned file layout |
| [MVP specification](docs/mvp-spec.md) | Schemas, validation rules, boundary behavior, and example API exchange |
| [Implementation plan](docs/implementation-plan.md) | Small coding tasks, acceptance criteria, checks, and suggested commits |
| [Test plan](docs/test-plan.md) | Reproducible inputs and expected results for pytest |

## Setup and execution status

**Available now:** the repository and these Markdown documents. Read the documents
and implement task 1 in the [implementation plan](docs/implementation-plan.md).

**Planned development baseline:** Python 3.12, Pydantic 2, FastAPI, pytest, and HTTPX
(for FastAPI's test client). The coding tasks will add a backend dependency manifest
with bounded major versions and record the resolved versions in a lockfile. These
files and dependencies have not been added or installed by this documentation work.

Once task 1 adds the dependency files, the intended setup from the repository root is:

```sh
python3.12 -m venv /workspace/.venvs/cs222-project
. /workspace/.venvs/cs222-project/bin/activate
python -m pip install -r backend/requirements.lock
```

For a local machine, substitute a virtual-environment path outside the checkout.
Do not run the install command until that lockfile exists. It should contain runtime
and test dependencies and be regenerated intentionally when dependencies change.

After the relevant implementation tasks are complete, the intended commands,
all from the repository root with the virtual environment activated, are:

```sh
# After models, validator, and their tests exist:
python -m pytest backend/tests

# After the API task adds app/main.py and the Uvicorn runtime dependency:
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --reload
```

These are future instructions, not claims of a working application or passing tests.
No environment variables, credentials, network services, or database should be
required to run the first MVP after installing dependencies.

## Longer-term direction

The proposed full stack is FastAPI/Pydantic, React/TypeScript, SQLite/SQLAlchemy,
OpenAI for candidate planning, and Google Places/Routes for external facts. Add
those components only after the validator milestone is reliable. External adapters
will supply structured facts; the validator will remain deterministic and independently
testable. See the architecture document for the boundary between planned components.
