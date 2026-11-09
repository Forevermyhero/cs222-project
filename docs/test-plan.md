# Tests and verification boundary

## Offline tests

From the repository root:

```sh
python -m flake8 src tests scripts
python -m pytest --cov=src/backend/app --cov-report=term-missing --cov-fail-under=90
```

An autouse fixture rejects real HTTP requests. Dates, input facts and expected
results are controlled. No key, live service, database or running server is required.

| File | Verified behavior |
| --- | --- |
| `tests/test_models.py` | Input types, costs, date/zone rules, duplicate IDs/facts, coordinates and required baseline |
| `tests/test_validator.py` | Core constraints, boundaries, exact amounts, DST, immutability and deterministic ordering |
| `tests/test_services.py` | Injected public responses, cache/throttle, malformed data, opening parser, scheduling and timezone/date-line handling |
| `tests/test_api.py` | Flask HTML/assets, JSON contracts, 200 semantic results, 422 input errors, 400/413/415 errors and explicit provider failures |
| `tests/test_research.py` | Honest demo/live/cache provenance, safe links, no booking claims, streamed progress before lookup completion, errors and bounded capacity |
| `tests/test_toolbox.py` | Independent typed tools, coordinates, raw tags, unknown prices, directed routes, invalid inputs and failure evidence |

The original fixed events must be compared with generated candidates. Merely proving
that the validator does not mutate its input is not sufficient.

## Actual local HTTP and browser checks

Use the README startup command. Submit both JSON examples and compare the planning
result with a separate `/validate` call. The interview must remain unchanged and a
manually overlapping flexible event must fail. An open port alone is not readiness.

`scripts.smoke_browser` exercises desktop/mobile input, five-event output,
revalidation, JSON export, the seven-step example log, source cards, unverified
preparation suggestions, event add/remove, error display and safe rendering of
user markup. It saves screenshots and the downloaded result to an ignored path.

`python -m scripts.smoke_tools` checks the portable bundle and backend demo.
Public API responses are injected: coordinates, raw opening tags, unknowns,
directional rounding, source URLs, cached routes, JSON export, offline/mobile
operation and explicit failures. It does not prove live provider availability.
Managed Chromium blocks file navigation, so the unchanged portable HTML bytes
are served at an intercepted local URL; browser policy is not modified.

## External checks

`scripts.smoke_live` deliberately contacts the four public map services. A service
or environment failure exits nonzero and never silently selects examples. Supported
opening coverage can legitimately remain incomplete.

No model API is connected in this revision. There is no claim of real LLM generation,
autonomous browsing, website scraping, inventory verification, purchases or bookings.
See [the validation report](validation-report.md) for executed results and access blockers.
