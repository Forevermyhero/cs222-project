import pytest

from backend.app.main import create_app
from backend.app.services.providers import ProviderError


def test_frontend_and_health(web):
    page = web.get("/")
    assert page.status_code == 200
    assert b"Itinerary That Holds Up" in page.data
    assert "script-src 'self'" in page.headers["Content-Security-Policy"]
    assert web.get("/static/app.js").status_code == 200
    assert web.get("/static/style.css").status_code == 200
    assert web.get("/api/health").get_json()["openai_configured"] is False


def test_validation_semantic_results_and_422(web, payload):
    assert web.post("/validate", json=payload).get_json() == {
        "is_valid": True, "violations": [], "warnings": [],
    }
    payload["trip"]["budget"] = "30.00"
    response = web.post("/validate", json=payload)
    assert response.status_code == 200
    assert response.get_json()["violations"][0]["code"] == "BUDGET_EXCEEDED"
    payload["trip"]["activities"][0]["start_time"] = "2026-11-16T09:00"
    invalid = web.post("/validate", json=payload)
    assert invalid.status_code == 422
    assert invalid.get_json()["detail"][0]["loc"][-1] == "start_time"


def test_plan_demo_roundtrip(web):
    data = web.get("/api/example").get_json()
    response = web.post("/api/plan", json=data)
    assert response.status_code == 200
    result = response.get_json()
    assert result["data_mode"] == "demo"
    assert result["fully_checked"]
    assert web.post("/validate", json=result["request"]).get_json() == result["validation"]
    data["planner"] = "openai"
    unavailable = web.post("/api/plan", json=data)
    assert unavailable.status_code == 503
    assert unavailable.get_json()["provider"] == "OpenAI"


def test_live_failure_does_not_silently_use_demo():
    class Unavailable:
        def city(self, destination):
            raise ProviderError("Open-Meteo", "Test service outage")
    app = create_app({"TESTING": True}, data_client=Unavailable())
    with app.test_client() as web:
        data = web.get("/api/example").get_json()
        data["data_mode"] = "live"
        response = web.post("/api/plan", json=data)
        assert response.status_code == 503
        assert response.get_json() == {"error": "Test service outage", "provider": "Open-Meteo"}


@pytest.mark.parametrize("kind,status", [("json", 400), ("mime", 415), ("size", 413)])
def test_bad_http_requests(web, kind, status):
    if kind == "json":
        response = web.post("/api/plan", data="{bad", content_type="application/json")
    elif kind == "mime":
        response = web.post("/api/plan", data="text")
    else:
        response = web.post("/api/plan", data="x" * 256_001, content_type="application/json")
    assert response.status_code == status
    assert "error" in response.get_json()
    assert web.get("/unknown").status_code == 404


def test_plan_input_error_and_configuration_is_private(web):
    data = web.get("/api/example").get_json()
    data["destination"] = "Paris"
    assert web.post("/api/plan", json=data).status_code == 422
    app = create_app({"TESTING": True, "PLANNER_API_KEY": "private-test-value"})
    with app.test_client() as client:
        response = client.get("/api/health")
        assert response.get_json()["openai_configured"]
        assert b"private-test-value" not in response.data
