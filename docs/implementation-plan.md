# Implementation status and next tasks

## Implemented

- Organized application code in `src/backend` and `src/frontend`, with separate tests.
- Flask JSON routes, a progress-stream endpoint, and a responsive trip form.
- Strict contracts and an independent validator with original fixed-event comparison.
- A deterministic candidate scheduler and an offline Chicago demonstration.
- No-key city, place/opening-tag and driving-route adapters.
- Visible request/cache/failure records, source links and unverified preparation advice.
- Offline regression tests, browser/live smoke scripts and CI configuration.
- English module comments and a [Chinese file-by-file explanation](code-tour.zh-CN.md).

Executed outcomes and unresolved access requirements are recorded in
[validation-report.md](validation-report.md). A successful mocked test does not
establish real external connectivity.

## 1. Verify real no-key services in the intended environment

Objective: confirm actual data access and coverage.
Files: `src/backend/app/services/providers.py`, `scripts/smoke_live.py`.
Guidance: enable the four documented domains and run the opt-in smoke script.
Acceptance: real geocoding, attraction lookup, explicit place lookup and routes
succeed, while missing opening information remains unverified.
Test: `python -m scripts.smoke_live --destination Chicago`.
Suggested commit: `test: record public data integration evidence`.

## 2. Confirm ambiguous places before planning

Objective: let the user approve resolved locations instead of accepting the first
geocoding match without review.
Files: providers, pipeline, frontend controller/render modules and tests.
Guidance: retain provider IDs, coordinates and attribution. Do not implement public
Nominatim autocomplete or bulk geocoding.
Acceptance: the user can confirm or reject a match without changing fixed times.
Test: ambiguous-name mocked responses and browser selection flow.
Suggested commit: `feat: confirm resolved places before planning`.

## 3. Add an optional LLM proposal/tool adapter

Objective: explore an eligible free-tier or local model without making the basic
prototype depend on an account or paid provider.
Files: a new service adapter, pipeline selection and contract tests.
Guidance: verify the chosen provider's current model, region, quota and billing
terms; configure any required key securely. Use bounded existing lookup methods
as tools, keep source URLs, and validate every generated candidate independently.
Acceptance: malformed output/unknown places are rejected; original commitments are
preserved or explicitly flagged. The UI identifies the actual planner used.
Test: injected model responses first, then an explicitly configured real request.
Suggested commit: `feat: add optional structured model planning`.

## 4. Add supported official-page research for missing facts

Objective: obtain cited facts when structured place data lacks opening information.
Guidance: select a bounded search/read mechanism, respect site rules, protect against
untrusted page instructions and unsafe URLs, and record source/freshness. A model's
unsupported claim must not become an authoritative opening or booking fact.
Acceptance: missing/conflicting facts remain visible; no booking action is taken.
Suggested commit: `feat: cite additional venue research sources`.

## 5. Flexible edits and limited repair

Objective: edit or replace flexible visits, then revalidate against the same baseline.
Guidance: copy the candidate and modify flexible events only; report unsatisfied
constraints when local changes cannot help.
Acceptance: original IDs, locations, times and fixed flags remain intact.
Test: valid edit, forbidden fixed edit, unrepairable fixed/fixed conflict.
Suggested commit: `feat: edit flexible visits with fixed-event protection`.

Each cloud task already has an isolated checkout; no additional Git worktree is
required. Review the actual diff and test evidence before merging a feature branch.
