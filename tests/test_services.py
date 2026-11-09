"""Provider and planner tests using injected responses, never a real online service."""

import copy
from datetime import date, datetime, timezone
from unittest.mock import Mock
from zoneinfo import ZoneInfo

import pytest
import requests

from src.backend.app.models import PlanRequest
from src.backend.app.services.demo import demo_places, example_request
from src.backend.app.services.opening_hours import expand_hours
from src.backend.app.services.pipeline import plan_trip
from src.backend.app.services.providers import ProviderError, PublicDataClient
from src.backend.app.time_utils import localize


class FakeSession:
    def __init__(self, payload=None, error=None):
        self.payload, self.error, self.calls = payload, error, []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if self.error:
            raise self.error
        response = Mock()
        response.content = b"{}"
        response.json.return_value = copy.deepcopy(self.payload)
        return response

    def post(self, url, **kwargs):
        return self.get(url, **kwargs)


class FakeMapClient:
    def __init__(self, route_error=False, attraction_error=False, missing_hours=False):
        self.route_error = route_error
        self.attraction_error = attraction_error
        self.missing_hours = missing_hours

    def city(self, destination):
        return demo_places()[0].location, "America/Chicago"

    def attractions(self, center):
        if self.attraction_error:
            raise ProviderError("Overpass", "Test Overpass outage")
        result = demo_places()[:2]
        if self.missing_hours:
            for place in result:
                place.opening_expression = "PH unknown"
        return result

    def find_place(self, name, destination):
        return demo_places()[0]

    def travel_matrix(self, locations):
        if self.route_error:
            raise ProviderError("OSRM", "Test OSRM outage")
        from src.backend.app.models import TravelTime
        return [TravelTime(from_location_id=a.id, to_location_id=b.id, minutes=10)
                for a in locations for b in locations if a.id != b.id]


def test_public_client_cache_and_transport_contract():
    session = FakeSession({"results": [{"id": 1, "name": "Chicago", "latitude": 41.88,
                                       "longitude": -87.63, "timezone": "America/Chicago"}]})
    client = PublicDataClient(session)
    point, zone = client.city("Chicago")
    assert zone == "America/Chicago" and point.latitude == 41.88
    assert client.city("Chicago") == (point, zone)
    assert len(session.calls) == 1
    assert session.calls[0][1]["timeout"] == (5, 20)
    assert "CS222" in session.calls[0][1]["headers"]["User-Agent"]
    # Expired cached entries must not be used indefinitely.
    for key, (_, data) in client.cache.items():
        client.cache[key] = (0, data)
    client.city("Chicago")
    assert len(session.calls) == 2


@pytest.mark.parametrize("payload", [{}, {"results": []}, None, []])
def test_bad_city(payload):
    with pytest.raises(ProviderError):
        PublicDataClient(FakeSession(payload)).city("Chicago")


@pytest.mark.parametrize("error", [requests.Timeout(), requests.HTTPError(), ValueError()])
def test_transport_failures_are_explicit(error):
    with pytest.raises(ProviderError, match="unavailable"):
        PublicDataClient(FakeSession(error=error)).city("Chicago")


def test_nominatim_extratags_and_rate_limit(monkeypatch):
    session = FakeSession([{"osm_type": "way", "osm_id": 42, "lat": "41.88", "lon": "-87.63",
                            "extratags": {"opening_hours": "24/7",
                                          "website": "https://venue.example/visit"}}])
    client = PublicDataClient(session)
    monkeypatch.setattr("src.backend.app.services.providers.time.monotonic", lambda: 100.0)
    sleep = Mock()
    monkeypatch.setattr("src.backend.app.services.providers.time.sleep", sleep)
    first = client.find_place("Museum", "Chicago")
    assert first.opening_expression == "24/7" and first.location.id == "osm:way:42"
    assert first.website == "https://venue.example/visit"
    client.find_place("Museum", "Chicago")
    sleep.assert_called_once()
    assert len(session.calls) == 1
    with pytest.raises(ProviderError, match="resolve"):
        PublicDataClient(FakeSession([])).find_place("Missing", "Chicago")


def test_overpass_skips_missing_names_or_coordinates():
    payload = {"elements": [
        {"type": "node", "id": 1, "lat": 41.88, "lon": -87.63,
         "tags": {"name": "Museum", "opening_hours": "Mo-Su 09:00-17:00",
                  "website": "javascript:alert(1)"}},
        {"type": "way", "id": 2, "center": {"lat": 41.9, "lon": -87.6},
         "tags": {"name": "Gallery", "contact:website": "https://gallery.example"}},
        {"type": "node", "id": 3, "tags": {}},
        {"type": "node", "id": 4, "tags": {"name": "No coordinates"}},
    ]}
    result = PublicDataClient(FakeSession(payload)).attractions(demo_places()[0].location)
    assert [p.location.name for p in result] == ["Gallery", "Museum"]
    assert result[0].website == "https://gallery.example"
    assert result[1].website is None
    with pytest.raises(ProviderError):
        PublicDataClient(FakeSession({"remark": "timeout"})).attractions(result[0].location)


def test_directed_routes_round_up_and_unknown_routes():
    points = [p.location for p in demo_places()[:2]]
    session = FakeSession({"code": "Ok", "durations": [[0, 61], [None, 0]]})
    client = PublicDataClient(session)
    result = client.travel_matrix(points)
    assert len(result) == 1
    assert result[0].minutes == 2
    assert result[0].from_location_id == points[0].id
    assert result[0].to_location_id == points[1].id
    assert client.travel_matrix(points[:1]) == []
    assert "/driving/" in session.calls[0][0]


@pytest.mark.parametrize("payload", [
    {"code": "NoTable"}, {"code": "Ok", "durations": [[0]]},
    {"code": "Ok", "durations": [[0, -1], [0, 0]]},
    {"code": "Ok", "durations": [[0, True], [0, 0]]},
])
def test_invalid_routes(payload):
    with pytest.raises(ProviderError):
        client = PublicDataClient(FakeSession(payload))
        client.travel_matrix([p.location for p in demo_places()[:2]])


@pytest.mark.parametrize("expression,count", [
    ("24/7", 1), ("Mo-Su 09:00-17:00", 2), ("Mo-Fr 09:00-17:00; Sa,Su off", 1),
    ("off", 0), ("Mo 09:00-12:00,13:00-17:00", 2), ("Su-Mo 22:00-02:00", 2),
])
def test_supported_opening_hours(expression, count):
    hours = expand_hours("place", expression, date(2026, 11, 16), date(2026, 11, 16),
                         "America/Chicago")
    assert hours is not None
    assert len(hours.windows) == count
    assert all(w.end_time.astimezone(timezone.utc) > w.start_time.astimezone(timezone.utc)
               for w in hours.windows)


@pytest.mark.parametrize("expression", [
    None, "", "PH off; Mo-Fr 09:00-17:00", "sunrise-sunset", "Mo 25:00-26:00",
    "Mo 24:00-01:00", "Mo 10:00-10:00",
])
def test_unsupported_hours_are_unknown(expression):
    assert expand_hours("p", expression, date(2026, 11, 16), date(2026, 11, 16), "UTC") is None


def test_local_clock_dst_roundtrip():
    zone = ZoneInfo("America/Chicago")
    assert localize(datetime(2026, 11, 16, 9), zone).utcoffset().total_seconds() == -6 * 3600
    for wall in (datetime(2026, 11, 1, 1, 30), datetime(2026, 3, 8, 2, 30)):
        with pytest.raises(ValueError, match="ambiguous or nonexistent"):
            localize(wall, zone)
    supplied = datetime.fromisoformat("2026-11-01T01:30:00-05:00")
    assert localize(supplied, zone).timestamp() == supplied.timestamp()


def test_demo_pipeline_preserves_baseline_and_is_repeatable():
    request = PlanRequest.model_validate(example_request())
    before = request.model_copy(deep=True)
    first = plan_trip(request)
    assert first == plan_trip(request)
    assert request == before
    assert first["validation"] == {"is_valid": True, "violations": [], "warnings": []}
    assert first["fully_checked"]
    assert len(first["request"]["trip"]["activities"]) == 5
    original = first["request"]["original_fixed_events"][0]
    generated = next(a for a in first["request"]["trip"]["activities"] if a["id"] == original["id"])
    assert original == generated
    assert "synthetic" in first["notes"][0]


@pytest.mark.parametrize("destination", ["Chicago", "芝加哥", "Chicago, IL"])
def test_sample_art_museum_alias_and_activity_origins(destination):
    data = example_request()
    data["destination"] = destination
    result = plan_trip(PlanRequest.model_validate(data))
    assert result["request"]["trip"]["destination"] == "Chicago"
    fixed = result["request"]["original_fixed_events"][0]
    assert fixed["name"] == "Hotel check-in"
    assert "15:00" in fixed["start_time"] and "15:30" in fixed["end_time"]
    summary = result["planning_summary"]
    assert summary["nearby_search"] == "sample_not_queried"
    assert len(summary["candidate_activities"]) == 4
    assert all("not fetched online" in c["reason"] for c in summary["candidate_activities"])
    names = [a["name"] for a in result["request"]["trip"]["activities"]]
    assert "Walk through Millennium Park" in names
    assert "Explore art at the Art Institute of Chicago" in names


def test_live_nearby_search_uses_the_requested_venue_and_explains_failures():
    from src.backend.app.models import Location

    class AnchoredClient(FakeMapClient):
        def city(self, destination):
            return Location(id="center", name="City center", latitude=41.0,
                            longitude=-87.0), "America/Chicago"

        def attractions(self, center):
            assert center.id == "demo:art"  # The requested museum, not the city center.
            return super().attractions(center)

    data = example_request()
    data.update(data_mode="live", fixed_events=[], budget=None)
    request = PlanRequest.model_validate(data)
    result = plan_trip(request, AnchoredClient())
    assert result["planning_summary"]["search_center"]["id"] == "demo:art"
    assert result["planning_summary"]["nearby_search"] == "completed"
    partial = plan_trip(request, AnchoredClient(attraction_error=True))
    assert partial["planning_summary"]["nearby_search"] == "failed"
    assert len(partial["planning_summary"]["candidate_activities"]) == 1
    assert any("no replacement nearby activities" in note for note in partial["notes"])


def test_nominatim_reports_the_matched_name_instead_of_echoing_a_broad_query():
    row = {"osm_type": "way", "osm_id": 42, "lat": "41.88", "lon": "-87.63",
           "display_name": "Art Institute of Chicago, Chicago, Illinois"}
    place = PublicDataClient(FakeSession([row])).find_place("Art Museum", "Chicago")
    assert place.location.name == "Art Institute of Chicago"


@pytest.mark.parametrize("status,expected_calls", [(403, 1), (429, 1), (503, 2), (504, 2)])
def test_overpass_retries_only_server_overload_on_the_same_host(status, expected_calls):
    class SequenceSession(FakeSession):
        def get(self, url, **kwargs):
            if not self.calls:
                self.calls.append((url, kwargs))
                response = Mock(status_code=status)
                raise requests.HTTPError(response=response)
            return super().get(url, **kwargs)

    session = SequenceSession({"elements": []})
    client = PublicDataClient(session)
    if expected_calls == 1:
        with pytest.raises(ProviderError, match=f"HTTP {status}"):
            client.attractions(demo_places()[0].location)
    else:
        assert client.attractions(demo_places()[0].location) == []
        assert "around:1500" in session.calls[-1][1]["params"]["data"]
    assert len(session.calls) == expected_calls
    assert {url for url, _ in session.calls} == {"https://overpass-api.de/api/interpreter"}


@pytest.mark.parametrize("error,reason", [
    (requests.exceptions.ProxyError(), "proxy connection failed"),
    (requests.ConnectionError(), "connection failed"),
])
def test_connection_diagnostics_do_not_retry_a_refused_network(error, reason):
    session = FakeSession(error=error)
    with pytest.raises(ProviderError, match=reason):
        PublicDataClient(session).attractions(demo_places()[0].location)
    assert len(session.calls) == 1


def test_live_pipeline_uses_mocked_providers_without_claiming_coverage():
    data = example_request()
    data.update(data_mode="live", fixed_events=[], requested_places=[], budget=None)
    request = PlanRequest.model_validate(data)
    result = plan_trip(request, FakeMapClient(route_error=True, missing_hours=True))
    assert result["data_mode"] == "live"
    assert not result["fully_checked"]
    codes = {w["code"] for w in result["validation"]["warnings"]}
    assert codes == {"MISSING_TRAVEL_TIME", "MISSING_OPENING_HOURS"}
    assert any("OSRM" in n for n in result["notes"])
    data.update(requested_places=["Art Institute of Chicago"], timezone="UTC")
    result = plan_trip(PlanRequest.model_validate(data), FakeMapClient(attraction_error=True))
    assert any("Destination timezone" in n for n in result["notes"])
    assert any("Overpass" in n for n in result["notes"])


def test_live_fixed_venues_keep_their_available_opening_information():
    data = example_request()
    data["data_mode"] = "live"
    data["budget"] = None
    result = plan_trip(PlanRequest.model_validate(data), FakeMapClient())
    original = result["request"]["original_fixed_events"][0]
    supplied = [h["location_id"] for h in result["request"]["opening_hours"]]
    assert supplied.count(original["location"]["id"]) == 1
    assert not result["validation"]["warnings"]
    assert result["validation"]["is_valid"]


def test_live_opening_hours_use_the_destination_clock_not_the_display_zone():
    data = example_request()
    data.update(data_mode="live", timezone="UTC", fixed_events=[], budget=None)
    result = plan_trip(PlanRequest.model_validate(data), FakeMapClient())
    windows = result["request"]["opening_hours"][0]["windows"]
    assert all(datetime.fromisoformat(w["start_time"]).utcoffset().total_seconds() == -6 * 3600
               for w in windows)
    assert result["request"]["trip"]["timezone"] == "UTC"
    assert result["validation"]["is_valid"]


def test_opening_calendar_dates_follow_the_destination_across_the_date_line():
    class DateLineClient(FakeMapClient):
        def city(self, destination):
            return demo_places()[0].location, "Pacific/Kiritimati"

        def attractions(self, center):
            places = demo_places()[:2]
            for place in places:
                place.opening_expression = "Tu 09:00-17:00"
            return places
    data = example_request()
    data.update(data_mode="live", timezone="Pacific/Honolulu", fixed_events=[],
                requested_places=[], budget=None, end_date="2026-11-16")
    result = plan_trip(PlanRequest.model_validate(data), DateLineClient())
    assert len(result["request"]["trip"]["activities"]) == 2
    assert result["validation"] == {"is_valid": True, "violations": [], "warnings": []}


@pytest.mark.parametrize("change", ["destination", "unknown_place", "bad_fixed", "outside_fixed"])
def test_invalid_demo_requests(change):
    data = example_request()
    if change == "destination":
        data["destination"] = "Paris"
    elif change == "unknown_place":
        data["requested_places"] = ["Unknown place"]
    elif change == "bad_fixed":
        data["fixed_events"][0]["end_time"] = data["fixed_events"][0]["start_time"]
    else:
        data["fixed_events"][0]["start_time"] = "2026-11-15T10:00"
    with pytest.raises(ValueError):
        plan_trip(PlanRequest.model_validate(data))


def test_no_slot_produces_explicit_unscheduled_note():
    data = example_request()
    data["end_date"] = data["start_date"]
    data["fixed_events"][0].update(start_time="2026-11-16T08:00", end_time="2026-11-16T20:00")
    result = plan_trip(PlanRequest.model_validate(data))
    assert len(result["unscheduled_places"]) == 4
    assert len(result["request"]["trip"]["activities"]) == 1


def test_generated_ids_do_not_collide_with_user_commitments():
    data = example_request()
    data["fixed_events"][0]["id"] = "visit:demo:art"
    result = plan_trip(PlanRequest.model_validate(data))
    ids = [a["id"] for a in result["request"]["trip"]["activities"]]
    assert len(ids) == len(set(ids)) == 5
    assert result["validation"]["is_valid"]
