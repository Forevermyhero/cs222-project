# Validation evidence

Recorded for the working tree on `feat/flask-itinerary-mvp`. This report concerns
the local implementation; it is not evidence of a push, merge, published deployment,
or completed remote GitHub Actions run.

## Passed

| Check | Executed outcome |
| --- | --- |
| Hash-locked clean installation | Installed `backend/requirements.lock` with `--require-hashes` into a new Python 3.12 virtual environment |
| Offline suite in clean environment | **122 passed**, no failed/skipped tests; application statement coverage **98.94%** |
| CI coverage gate | Required 90% reached |
| Style | `python -m flake8 backend scripts` passed |
| Dependency consistency | `python -m pip check` reported no broken requirements |
| Real local HTTP | Health, example input, planning, original fixed-event preservation, overlap detection and 422 malformed input |
| Desktop browser | Example loading, five scheduled events including the unchanged interview, revalidation and JSON download |
| Mobile browser | 390px viewport, event add/remove, planning, no horizontal overflow |
| Browser safety/errors | User markup rendered as text; deliberate invalid destination displayed an error; no page JavaScript errors |

The deterministic example schedules four flexible Chicago visits around one fixed
interview and passes all checks against its **synthetic** facts. Displayed hours,
prices, meeting coordinates and travel durations are not claimed as real conditions.

The suite includes DST and date-line regressions: provider opening times use the
destination's clock/calendar while activity displays can use a different trip zone.
It also tests independent fixed-event comparison, ungrounded AI prices, duplicate
generated/user IDs and shared-venue facts.

Browser screenshots and exported results were generated under the task's scratch
directory. The reusable browser script can regenerate them under ignored
`test-results/browser/`; these generated files are not required application inputs.

## Live public APIs: blocked in this cloud instance

A real HTTPS request to the Open-Meteo geocoding endpoint was attempted with the
inherited proxy and TLS verification. The sandbox could not connect to its proxy;
an approved outer-executor retry returned `CONNECT tunnel failed, response 403`.
The applied cloud network policy did not include the requested public-data domains.
This is an environment access blocker, not a demonstrated provider outage.

The following exact domains were saved in an environment configuration draft:

- `geocoding-api.open-meteo.com`
- `nominatim.openstreetmap.org`
- `overpass-api.de`
- `router.project-osrm.org`

Saving the draft did not apply or publish it. At the last runtime observation, the
applied custom allowlist was still empty. Review/save the changes in environment
settings and publish the environment, then recheck current status and run:

```sh
python -m scripts.smoke_live --destination Chicago
```

The adapters have passed mocked response/failure tests. A successful real public
API round trip has **not** been claimed. The live smoke script is opt-in and exits
nonzero if an essential service fails; it does not fall back to demo fixtures.

## Optional AI: mocked tests only

No usable AI key/model binding was present. OpenAI HTTP contracts, malformed
responses, trusted places/prices, and independent validation were tested with
injected responses. No live LLM request or free LLM availability is claimed.
The optional server adapter requires a securely configured key/model and outbound
access to `api.openai.com`. The no-key default remains the labeled heuristic planner.

## Not implemented / not executed

- Persistence, automatic repair, transit/walking routing and global optimization.
- A remote CI run or public deployment.
- Real-provider validation in a newly published cloud snapshot.

No model assertions were disabled and no unknown facts were replaced with invented
opening hours, travel estimates or prices in live mode.
