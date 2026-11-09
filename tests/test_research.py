"""Research evidence, streaming behavior and booking-link honesty."""

import json
import threading

import pytest

from src.backend.app.main import create_app
from src.backend.app.models import PlanRequest
from src.backend.app.services.demo import example_request
from src.backend.app.services.pipeline import plan_trip
from src.backend.app.services.providers import ProviderError, PublicDataClient
from src.backend.app.services.research import ResearchLog, map_link, safe_link
from src.backend.app.streaming import stream_plan
from tests.test_services import FakeSession


def decode(response):
    return [json.loads(line) for line in response.get_data(as_text=True).splitlines()]


def test_demo_trace_never_claims_to_have_visited_a_website():
    events = []
    result = plan_trip(PlanRequest.model_validate(example_request()), progress=events.append)
    assert len(result["research_steps"]) == 7
    assert all(not step["network_request"] for step in result["research_steps"])
    assert any(step["status"] == "example" for step in result["research_steps"])
    assert all(event["type"] == "progress" for event in events)
    assert len(events) > len(result["research_steps"])  # Running rows become completed rows.
    assert all(not source["website_checked"] for source in result["sources"])
    assert all(item["booking_required"] is None and not item["availability_checked"]
               for item in result["preparation"])
    assert any(item["url"] for item in result["preparation"])


def test_real_request_and_cache_evidence_are_distinct_and_request_local():
    payload = {"results": [{"id": 1, "name": "Chicago", "latitude": 41.88,
                            "longitude": -87.63, "timezone": "America/Chicago"}]}
    session = FakeSession(payload)
    shared = PublicDataClient(session)
    first, second = ResearchLog("live"), ResearchLog("live")
    shared.with_observer(first.provider_event).city("Chicago")
    shared.with_observer(second.provider_event).city("Chicago")
    assert len(session.calls) == 1
    assert first.steps[0]["status"] == "completed" and first.steps[0]["network_request"]
    assert second.steps[0]["status"] == "cached" and not second.steps[0]["network_request"]
    assert "geocoding-api.open-meteo.com/v1/search?" in first.steps[0]["url"]
    assert len(first.steps) == len(second.steps) == 1


@pytest.mark.parametrize("value", [
    None, "javascript:alert(1)", "data:text/html,test", "https://user:password@example.com",
    "https://a\nb.com", "https://a\\b.com", "not a URL",
])
def test_unsafe_reference_links_are_not_published(value):
    assert safe_link(value) is None


def test_source_urls_are_map_records_not_claimed_venue_visits():
    assert map_link("osm:way:42") == "https://www.openstreetmap.org/way/42"
    assert map_link("demo:art") is None
    assert map_link("osm:node:not-a-number") is None
    assert safe_link("https://venue.example/visit") == "https://venue.example/visit"


def test_streamed_example_includes_progress_then_exactly_one_result(web):
    sample = web.get("/api/example").get_json()
    response = web.post("/api/plan/stream", json=sample)
    assert response.status_code == 200
    assert response.mimetype == "application/x-ndjson"
    assert response.headers["Cache-Control"] == "no-store"
    events = decode(response)
    assert events[0]["type"] == "progress"
    assert events[-1]["type"] == "result"
    assert sum(event["type"] == "result" for event in events) == 1
    data = events[-1]["result"]
    assert data["validation"] == {"is_valid": True, "violations": [], "warnings": []}
    assert len(data["request"]["trip"]["activities"]) == 5
    assert data["research_steps"][-1]["status"] == "completed"
    invalid = web.post("/api/plan/stream", json={"destination": "Chicago"})
    assert invalid.status_code == 422 and invalid.mimetype == "application/json"


def test_progress_arrives_before_a_slow_lookup_finishes():
    entered, release = threading.Event(), threading.Event()

    class SlowUnavailable:
        def city(self, destination):
            entered.set()
            release.wait(timeout=2)
            raise ProviderError("Open-Meteo", "Test blocked lookup")

    app = create_app({"TESTING": True}, data_client=SlowUnavailable())
    with app.test_client() as web:
        data = example_request()
        data["data_mode"] = "live"
        response = web.post("/api/plan/stream", json=data, buffered=False)
        assert entered.wait(timeout=1)
        iterator = iter(response.response)
        first = json.loads(next(iterator))
        assert first["type"] == "progress"
        assert not release.is_set()
        release.set()
        remainder = [json.loads(line) for chunk in iterator for line in chunk.splitlines()]
        assert remainder[-1]["type"] == "error"
        assert remainder[-1]["status"] == 503
        assert all(event["type"] != "result" for event in remainder)
        response.close()


def test_stream_errors_do_not_expose_internal_exception_details():
    class Broken:
        def city(self, destination):
            raise RuntimeError("private-internal-detail")
    app = create_app({"TESTING": True}, data_client=Broken())
    with app.test_client() as web:
        data = example_request()
        data["data_mode"] = "live"
        events = decode(web.post("/api/plan/stream", json=data))
        assert events[-1]["status"] == 500
        assert "private-internal-detail" not in json.dumps(events)


def test_stream_capacity_is_bounded():
    with pytest.raises(ProviderError, match="already running"):
        stream_plan(None, None, threading.BoundedSemaphore(0), None)
