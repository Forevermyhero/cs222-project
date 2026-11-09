"""Candidate generators. Their output must pass the independent validator."""

import json
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

import requests
from pydantic import ValidationError

from ..models import Activity, Trip
from ..time_utils import localize
from ..validator import merge_windows, utc
from .providers import ProviderError


def heuristic_plan(request, fixed, places, travel, hours):
    """Place 60-minute visits in 09:00–18:00 slots around immutable commitments."""
    activities = [a.model_copy(deep=True) for a in fixed]
    travel_lookup = {(t.from_location_id, t.to_location_id): t.minutes for t in travel}
    hours_lookup = {h.location_id: merge_windows(h.windows) for h in hours}
    unscheduled = []
    zone = ZoneInfo(request.timezone)
    for place in places:
        activity_id = f"visit:{place.location.id}"
        suffix = 1
        while activity_id in {a.id for a in activities}:
            activity_id = f"visit:{place.location.id}:{suffix}"
            suffix += 1
        placed = False
        day = request.start_date
        while day <= request.end_date and not placed:
            for minute in range(9 * 60, 17 * 60 + 1, 15):
                start = localize(datetime.combine(day, time.min) + timedelta(minutes=minute), zone)
                end = (utc(start) + timedelta(hours=1)).astimezone(zone)
                windows = hours_lookup.get(place.location.id)
                if windows is not None and not any(
                    a <= utc(start) and utc(end) <= b for a, b in windows
                ):
                    continue
                candidate = Activity(id=activity_id, name=place.location.name,
                                     location=place.location, start_time=start, end_time=end,
                                     estimated_cost=place.estimated_cost)
                if fits(candidate, activities, travel_lookup):
                    activities.append(candidate)
                    placed = True
                    break
            day += timedelta(days=1)
        if not placed:
            unscheduled.append(place.location.name)
    return activities, unscheduled


def fits(candidate, activities, travel):
    ordered = sorted(activities + [candidate], key=lambda a: (utc(a.start_time), a.id))
    for a, b in zip(ordered, ordered[1:]):
        if utc(a.end_time) > utc(b.start_time):
            return False
        # Only consider new legs affected by the insertion. Unknown legs get a planning
        # buffer, but are deliberately not turned into facts for the validator.
        if candidate not in (a, b):
            continue
        minutes = 0 if a.location.id == b.location.id else travel.get(
            (a.location.id, b.location.id), 30)
        if utc(b.start_time) - utc(a.end_time) < timedelta(minutes=minutes):
            return False
    return True


def openai_plan(request, fixed, places, api_key, model, session=None):
    """Optional paid/user-provided OpenAI service. No claim of a free LLM endpoint."""
    if not api_key:
        raise ProviderError("OpenAI", "OpenAI planning is not configured. Use heuristic planning "
                            "or configure PLANNER_API_KEY securely on the server.")
    session = session or requests.Session()
    instructions = (
        "Return a JSON object with only an 'activities' array. Plan a realistic itinerary using "
        "only the supplied places. Copy every original fixed event exactly, including its ID, "
        "name, location and offset-aware timestamps. Flexible visits need unique IDs, name, "
        "location, start_time/end_time (ISO strings with UTC offsets), fixed=false, and "
        "priority='medium'. Use estimated_cost=null when price is unknown. Do not invent "
        "places, hours, travel facts, or prices. Dates are inclusive in the trip timezone."
    )
    known = {p.location.id: p.location for p in places}
    known.update({a.location.id: a.location for a in fixed})
    place_costs = {p.location.id: p.estimated_cost for p in places}
    fixed_costs = {a.id: a.estimated_cost for a in fixed}
    context = {
        "trip_request": request.model_dump(mode="json"),
        "original_fixed_events": [a.model_dump(mode="json") for a in fixed],
        "places": [{"location": known[p.location.id].model_dump(mode="json"),
                    "estimated_cost": str(p.estimated_cost)
                    if p.estimated_cost is not None else None} for p in places],
    }
    payload = {
        "model": model, "response_format": {"type": "json_object"},
        "messages": [{"role": "system", "content": instructions},
                     {"role": "user", "content": json.dumps(context)}],
    }
    try:
        response = session.post("https://api.openai.com/v1/chat/completions", json=payload,
                                headers={"Authorization": f"Bearer {api_key}"}, timeout=(5, 40))
        response.raise_for_status()
        content = json.loads(response.json()["choices"][0]["message"]["content"])
        if not isinstance(content, dict) or set(content) != {"activities"}:
            raise ValueError("Unexpected generation schema")
        # Trip checks duplicate IDs and limits, in addition to parsing every Activity.
        candidate = Trip(**{k: getattr(request, k) for k in
                            ("destination", "start_date", "end_date", "timezone", "preferences")},
                         budget=request.budget, activities=content["activities"])
        for activity in candidate.activities:
            if known.get(activity.location.id) != activity.location:
                raise ValueError("The AI returned an unknown or changed place")
            # Suggested prices are not provider facts. Unknown prices remain unknown.
            activity.estimated_cost = (fixed_costs[activity.id] if activity.id in fixed_costs
                                       else place_costs.get(activity.location.id))
        return candidate.activities, []
    except (requests.RequestException, ValueError, KeyError, IndexError,
            TypeError, ValidationError):
        raise ProviderError("OpenAI", "The AI service failed or returned malformed/unknown-place "
                            "activities. No fallback was silently substituted.")
