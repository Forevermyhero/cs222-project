"""Explicitly synthetic Chicago fixtures; never returned as live provider data."""

from decimal import Decimal

from ..models import Location
from .providers import Place


def canonical_destination(value):
    aliases = {"chicago", "chicago, il", "chicago, illinois", "芝加哥"}
    return "Chicago" if value.strip().casefold() in aliases else value.strip()


def demo_requested_ids(names, places):
    """A few explicit sample aliases, not a general semantic search engine."""
    aliases = {"art museum": "demo:art", "art museums": "demo:art",
               "美术馆": "demo:art", "艺术博物馆": "demo:art"}
    selected = set()
    for name in names:
        matches = [p.location.id for p in places if
                   name.casefold() in p.location.name.casefold()
                   or aliases.get(name.strip().casefold()) == p.location.id]
        if not matches:
            raise ValueError(f'The sample does not contain "{name}". '
                             "Use public map data to look up other places.")
        selected.update(matches)
    return selected


def demo_places():
    rows = [
        ("art", "Art Institute of Chicago", 41.8796, -87.6237, "Mo-Su 10:00-17:00", "35.00"),
        ("park", "Millennium Park", 41.8826, -87.6226, "Mo-Su 08:00-20:00", "0.00"),
        ("river", "Chicago Riverwalk", 41.8882, -87.6262, "Mo-Su 08:00-20:00", "0.00"),
        ("museum", "Field Museum", 41.8663, -87.6170, "Mo-Su 09:00-17:00", "30.00"),
    ]
    # Reference links are useful to a traveler, but are not fetched or verified in demo mode.
    references = {"art": "https://www.artic.edu/visit",
                  "museum": "https://www.fieldmuseum.org/visit"}
    activities = {"art": "Explore art at the Art Institute of Chicago",
                  "park": "Walk through Millennium Park",
                  "river": "Stroll along the Chicago Riverwalk",
                  "museum": "Explore the Field Museum exhibits"}
    return [Place(Location(id=f"demo:{key}", name=name, latitude=lat, longitude=lon),
                  hours, Decimal(cost), references.get(key), activities[key])
            for key, name, lat, lon, hours, cost in rows]


def example_request():
    return {
        "destination": "Chicago", "start_date": "2026-11-16", "end_date": "2026-11-17",
        "timezone": "America/Chicago", "preferences": ["museums", "architecture"],
        "requested_places": ["Art Museum"], "budget": "100.00",
        "data_mode": "demo", "planner": "heuristic", "fixed_events": [{
            "id": "hotel-check-in", "name": "Hotel check-in", "location": "Palmer House",
            "start_time": "2026-11-16T15:00", "end_time": "2026-11-16T15:30",
        }],
    }
