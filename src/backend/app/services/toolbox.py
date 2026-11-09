"""Small, typed map tools usable without a planner or language model."""

from pydantic import Field, model_validator
from werkzeug.exceptions import NotFound

from ..models import Location, Model, Text, unique
from .providers import ProviderError
from .research import ResearchLog, map_link


class CityInput(Model):
    destination: Text


class PlaceInput(CityInput):
    name: Text


class NearbyInput(Model):
    center: Location

    @model_validator(mode="after")
    def coordinates(self):
        if self.center.latitude is None:
            raise ValueError("The center needs coordinates.")
        return self


class RoutesInput(Model):
    locations: list[Location] = Field(min_length=2, max_length=20)

    @model_validator(mode="after")
    def coordinates(self):
        unique([p.id for p in self.locations], "route location ID")
        if any(p.latitude is None for p in self.locations):
            raise ValueError("Every route location needs coordinates.")
        return self


TOOLS = {
    "city": (CityInput, "City coordinates and timezone / Open-Meteo"),
    "place": (PlaceInput, "One explicit place or address / Nominatim"),
    "attractions": (NearbyInput, "Nearby museums, galleries and attractions / Overpass"),
    "routes": (RoutesInput, "Directed driving-time estimates / OSRM"),
}


def catalog():
    return [{"name": name, "description": description, "input_schema": model.model_json_schema()}
            for name, (model, description) in TOOLS.items()]


def place_record(place):
    return {"location": place.location.model_dump(mode="json"),
            "opening_hours_raw": place.opening_expression, "website": place.website,
            "source_url": map_link(place.location.id), "website_checked": False,
            "cross_checked": False, "ticket_price": None, "hotel_availability": None}


def execute_tool(name, payload, client):
    """Return facts and their lookup records; never generate or repair a schedule."""
    if name not in TOOLS:
        raise NotFound("Unknown map tool.")
    parsed = TOOLS[name][0].model_validate(payload)
    log = ResearchLog("live")
    if hasattr(client, "with_observer"):
        client = client.with_observer(log.provider_event)
    try:
        if name == "city":
            location, timezone = client.city(parsed.destination)
            data = {"location": location.model_dump(mode="json"), "timezone": timezone}
        elif name == "place":
            data = place_record(client.find_place(parsed.name, parsed.destination))
        elif name == "attractions":
            data = [place_record(p) for p in client.attractions(parsed.center)]
        else:
            data = {"mode": "driving", "live_traffic": False,
                    "travel_times": [t.model_dump(mode="json")
                                     for t in client.travel_matrix(parsed.locations)],
                    "distance_meters": None}
    except ProviderError as error:
        error.research_steps = log.steps
        raise
    return {"tool": name, "data_mode": "live", "data": data, "research_steps": log.steps}
