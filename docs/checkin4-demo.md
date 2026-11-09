# Check-In #4: short demonstration guide

## A three-minute walkthrough

1. Open the main branch and `docs/code-tour.zh-CN.md` to locate the modules.
2. Run the README startup command from the repository root.
3. Load the Chicago example. Point out the fixed interview, destination, dates and desired place.
4. Click **Build & check my itinerary**. Show the unchanged interview and four flexible visits.
5. **Research log** opens above the results and stays open. Use **Previous step** / **Next step**,
   or click a step title, to explain each recorded operation. **Follow latest** tracks new updates.
   Reviewing a record does not repeat a lookup. Explain that the example is offline and labeled.
6. Open **Before you go**. These are links and suggestions to verify, not confirmed ticket requirements.
7. Download the JSON; it includes the authoritative fixed-event baseline and the research records.
8. If live access is available, switch to public data and inspect actual source URLs/cache labels.
   If access is blocked, show the failure as an access issue rather than a successful lookup.

## Suggested English introduction

> I used AI-assisted implementation to build a small form-to-itinerary prototype.
> The frontend sends structured trip requirements to Flask. The backend retains
> the original fixed events, gathers example or public map facts, proposes a
> schedule, and runs an independent Python validator. I added a research log so
> users can see source requests, cache hits and failures, and can distinguish
> example data from actual lookups. The current planner is deterministic; an LLM
> and autonomous browsing are future integration work. The system only proposes
> a plan and preparation steps. It does not book or purchase anything.

Use this wording only for the AI-assisted work you actually participated in or reviewed.
Explain your understanding of one concrete path rather than claiming every module
was independently written by you.

## A useful design point to explain

A candidate marked `fixed=true` is not enough. The server keeps the original fixed
events separately and compares IDs, names, locations and UTC start/end instants.
A model could generate a nonoverlapping schedule that moved an interview; the
independent baseline check must still reject that schedule.

## Current limitations worth discussing

- Public map destinations were initially blocked by this cloud's applied allowlist.
- OSM opening information can be missing, outdated or unsupported by the parser.
- Website links do not prove current opening hours, ticket inventory or booking policy.
- The greedy scheduler is a prototype, not a preference/global optimizer.
- No LLM, arbitrary web crawler, persistence or automatic repair is connected.

## Questions for staff

- Is one city with driving-time estimates a reasonable integration target first?
- How should incomplete opening-hour evidence affect the user-facing validity label?
- Is the original-fixed-events comparison a suitable interface boundary for later LLM work?

The meeting asks for real work and a reasonable next step; unfinished integrations
are appropriate to discuss. No presentation or specially invented artifact is required.
