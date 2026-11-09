"""Shared fixtures: reproducible trips and a guard that forbids accidental real HTTP."""

import copy

import pytest
import requests

from src.backend.app.main import create_app
from src.backend.app.models import ValidationRequest


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Offline tests must use an injected provider/session, not real HTTP.")
    monkeypatch.setattr(requests.Session, "request", forbidden)


@pytest.fixture
def payload():
    interview = {
        "id": "interview", "name": "Interview",
        "location": {"id": "office", "name": "Office"},
        "start_time": "2026-11-16T09:00:00-06:00",
        "end_time": "2026-11-16T10:00:00-06:00",
        "estimated_cost": "0.00", "fixed": True,
    }
    museum = {
        "id": "museum", "name": "Museum",
        "location": {"id": "museum", "name": "Museum"},
        "start_time": "2026-11-16T10:30:00-06:00",
        "end_time": "2026-11-16T12:00:00-06:00",
        "estimated_cost": "35.00", "fixed": False,
    }
    return {
        "trip": {"destination": "Chicago", "start_date": "2026-11-16",
                 "end_date": "2026-11-16", "timezone": "America/Chicago", "budget": "60.00",
                 "activities": [interview, museum]},
        "original_fixed_events": [copy.deepcopy(interview)],
        "travel_times": [{"from_location_id": "office", "to_location_id": "museum", "minutes": 20}],
        "opening_hours": [{"location_id": name, "windows": [{
            "start_time": "2026-11-16T08:00:00-06:00", "end_time": "2026-11-16T18:00:00-06:00",
        }]} for name in ("office", "museum")],
    }


@pytest.fixture
def parsed(payload):
    return ValidationRequest.model_validate(payload)


@pytest.fixture
def web():
    app = create_app({"TESTING": True})
    with app.test_client() as client:
        yield client
