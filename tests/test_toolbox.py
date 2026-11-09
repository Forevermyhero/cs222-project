"""Typed tools expose facts independently of planning; all provider data is injected."""

import pytest
import requests

from src.backend.app.main import create_app
from src.backend.app.models import Location, TravelTime
from src.backend.app.services.providers import Place, PublicDataClient


class FixtureTools:
    a = Location(id="osm:node:1", name="Museum", latitude=41.88, longitude=-87.62)
    b = Location(id="osm:node:2", name="Gallery", latitude=41.89, longitude=-87.63)

    def city(self, destination):
        assert destination == "Chicago"
        return self.a, "America/Chicago"

    def find_place(self, name, destination):
        assert (name, destination) == ("Museum", "Chicago")
        return Place(self.a, "Mo-Fr 09:00-17:00", website="https://example.org/visit")

    def attractions(self, center):
        assert center == self.a
        return [Place(self.a, "Mo-Fr 09:00-17:00"), Place(self.b)]

    def travel_matrix(self, locations):
        assert locations == [self.a, self.b]
        return [TravelTime(from_location_id=self.a.id, to_location_id=self.b.id, minutes=17),
                TravelTime(from_location_id=self.b.id, to_location_id=self.a.id, minutes=19)]


def test_tools_catalog_page_and_independent_calls():
    app = create_app({"TESTING": True}, data_client=FixtureTools())
    a, b = [p.model_dump(mode="json") for p in (FixtureTools.a, FixtureTools.b)]
    with app.test_client() as web:
        assert web.get("/tools").status_code == 200
        assert web.get("/static/tools.js").status_code == 200
        assert web.get("/static/tools.css").status_code == 200
        registry = web.get("/api/tools").get_json()
        assert not registry["llm_connected"]
        assert {t["name"] for t in registry["tools"]} == {
            "city", "place", "attractions", "routes",
        }
        assert "input_schema" in registry["tools"][0]
        city = web.post("/api/tools/city", json={"destination": "Chicago"}).get_json()
        assert city["data"] == {"location": a, "timezone": "America/Chicago"}
        place = web.post("/api/tools/place", json={
            "destination": "Chicago", "name": "Museum",
        }).get_json()["data"]
        assert place["opening_hours_raw"] == "Mo-Fr 09:00-17:00"
        assert place["source_url"] == "https://www.openstreetmap.org/node/1"
        assert not place["website_checked"] and not place["cross_checked"]
        assert place["ticket_price"] is None and place["hotel_availability"] is None
        nearby = web.post("/api/tools/attractions", json={"center": a}).get_json()["data"]
        assert nearby[1]["opening_hours_raw"] is None
        routes = web.post("/api/tools/routes", json={"locations": [a, b]}).get_json()["data"]
        assert [t["minutes"] for t in routes["travel_times"]] == [17, 19]
        assert routes["mode"] == "driving" and not routes["live_traffic"]
        assert routes["distance_meters"] is None
        assert web.post("/api/tools/unknown", json={}).status_code == 404


@pytest.mark.parametrize("name,payload", [
    ("city", {"destination": "  "}),
    ("city", {"destination": "Chicago", "url": "http://example.org"}),
    ("place", {"destination": "Chicago"}),
    ("attractions", {"center": {"id": "a", "name": "a"}}),
    ("routes", {"locations": [FixtureTools.a.model_dump()]}),
    ("routes", {"locations": [FixtureTools.a.model_dump()] * 2}),
    ("routes", {"locations": [FixtureTools.a.model_dump(), {"id": "b", "name": "b"}]}),
])
def test_tool_inputs_rejected_before_network(web, name, payload):
    assert web.post(f"/api/tools/{name}", json=payload).status_code == 422


def test_failed_tool_retains_provider_evidence_and_has_no_demo_substitute():
    class FailedSession:
        def get(self, *args, **kwargs):
            raise requests.Timeout("Injected unavailable service")
    client = PublicDataClient(session=FailedSession())
    app = create_app({"TESTING": True}, data_client=client)
    with app.test_client() as web:
        response = web.post("/api/tools/city", json={"destination": "Chicago"})
        assert response.status_code == 503
        data = response.get_json()
        assert "data" not in data
        assert data["research_steps"][0]["status"] == "failed"
        assert data["research_steps"][0]["url"].startswith(
            "https://geocoding-api.open-meteo.com/v1/search?")
