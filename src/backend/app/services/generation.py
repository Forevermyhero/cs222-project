"""Free, local candidate scheduler. Its output always passes through the separate validator.

A future LLM can replace this proposal step while retaining the same data contracts.
This module does not call any model service.
"""

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo


from ..models import Activity
from ..time_utils import localize
from ..validator import merge_windows, utc


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
