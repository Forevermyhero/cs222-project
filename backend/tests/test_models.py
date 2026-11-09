import copy

import pytest
from pydantic import ValidationError

from backend.app.models import Activity, PlanRequest, ValidationRequest
from backend.app.services.demo import example_request


@pytest.mark.parametrize("field,value", [
    ("start_time", "2026-11-16T10:30:00"), ("start_time", 1700000000),
    ("estimated_cost", "-1"), ("estimated_cost", "0.001"),
    ("estimated_cost", "NaN"), ("estimated_cost", "Infinity"),
    ("id", "  "), ("name", ""), ("priority", "urgent"), ("fixed", 1),
])
def test_bad_activity(payload, field, value):
    payload["trip"]["activities"][1][field] = value
    with pytest.raises(ValidationError):
        ValidationRequest.model_validate(payload)


@pytest.mark.parametrize("field,value", [
    ("destination", " "), ("timezone", "not/a/timezone"), ("currency", "EUR"),
    ("budget", "-1"), ("start_date", "2026-11-18"), ("start_date", 1700000000),
    ("start_date", "2026-11-16T00:00:00"),
    ("end_date", "9999-12-31"), ("end_date", "2026-12-01"),
    ("preferences", [""]),
])
def test_bad_trip(payload, field, value):
    payload["trip"][field] = value
    with pytest.raises(ValidationError):
        ValidationRequest.model_validate(payload)


@pytest.mark.parametrize("change", [
    "duplicate_activity", "duplicate_travel", "duplicate_hours", "unknown_place", "self_pair",
    "bad_window", "naive_window", "fixed_false", "missing_baseline", "unknown_field",
])
def test_bad_cross_fields(payload, change):
    if change == "duplicate_activity":
        payload["trip"]["activities"].append(copy.deepcopy(payload["trip"]["activities"][0]))
    elif change == "duplicate_travel":
        payload["travel_times"] *= 2
    elif change == "duplicate_hours":
        payload["opening_hours"] *= 2
    elif change == "unknown_place":
        payload["travel_times"][0]["to_location_id"] = "elsewhere"
    elif change == "self_pair":
        payload["travel_times"][0]["to_location_id"] = "office"
    elif change == "bad_window":
        window = payload["opening_hours"][0]["windows"][0]
        window["end_time"] = window["start_time"]
    elif change == "naive_window":
        payload["opening_hours"][0]["windows"][0]["start_time"] = "2026-11-16T08:00"
    elif change == "fixed_false":
        payload["original_fixed_events"][0]["fixed"] = False
    elif change == "missing_baseline":
        del payload["original_fixed_events"]
    else:
        payload["typo"] = 1
    with pytest.raises(ValidationError):
        ValidationRequest.model_validate(payload)


@pytest.mark.parametrize("minutes", [-1, 1.5, True, "20"])
def test_strict_travel_minutes(payload, minutes):
    payload["travel_times"][0]["minutes"] = minutes
    with pytest.raises(ValidationError):
        ValidationRequest.model_validate(payload)


def test_coordinates_are_paired(payload):
    payload["trip"]["activities"][1]["location"]["latitude"] = 41.0
    with pytest.raises(ValidationError):
        ValidationRequest.model_validate(payload)


def test_defaults_and_semantic_interval(payload):
    a = copy.deepcopy(payload["trip"]["activities"][1])
    a["end_time"] = "2026-11-16T09:00:00-06:00"
    parsed = Activity.model_validate(a)
    assert parsed.priority == "medium"
    first = ValidationRequest.model_validate(payload)
    second = ValidationRequest.model_validate(payload)
    first.trip.preferences.append("museum")
    assert second.trip.preferences == []


def test_plan_contract():
    assert PlanRequest.model_validate(example_request()).planner == "heuristic"
    data = example_request()
    data["fixed_events"][0]["latitude"] = 41.0
    with pytest.raises(ValidationError):
        PlanRequest.model_validate(data)
