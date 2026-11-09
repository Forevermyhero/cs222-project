"""Explicitly synthetic Chicago fixtures; never returned as live provider data."""

from decimal import Decimal

from ..models import Location
from .providers import Place


def demo_places():
    rows = [
        ("art", "Art Institute of Chicago", 41.8796, -87.6237, "Mo-Su 10:00-17:00", "35.00"),
        ("park", "Millennium Park", 41.8826, -87.6226, "Mo-Su 08:00-20:00", "0.00"),
        ("river", "Chicago Riverwalk", 41.8882, -87.6262, "Mo-Su 08:00-20:00", "0.00"),
        ("museum", "Field Museum", 41.8663, -87.6170, "Mo-Su 09:00-17:00", "30.00"),
    ]
    return [Place(Location(id=f"demo:{key}", name=name, latitude=lat, longitude=lon),
                  hours, Decimal(cost)) for key, name, lat, lon, hours, cost in rows]


def example_request():
    return {
        "destination": "Chicago", "start_date": "2026-11-16", "end_date": "2026-11-17",
        "timezone": "America/Chicago", "preferences": ["museums", "architecture"],
        "requested_places": ["Art Institute of Chicago"], "budget": "100.00",
        "data_mode": "demo", "planner": "heuristic", "fixed_events": [{
            "id": "interview", "name": "Interview", "location": "Demo office",
            "start_time": "2026-11-16T10:00", "end_time": "2026-11-16T11:00",
        }],
    }
