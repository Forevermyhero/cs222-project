"""Pure-rule tests: constraints, timezone boundaries, stable results and no mutation."""

import copy
from datetime import datetime, timezone

import pytest

from src.backend.app.models import ValidationRequest
from src.backend.app.validator import validate_itinerary


def result(payload):
    return validate_itinerary(ValidationRequest.model_validate(payload))


def codes(items):
    return [item.code for item in items]


def test_valid_and_immutable(parsed):
    before = parsed.model_copy(deep=True)
    checked = validate_itinerary(parsed)
    assert checked.is_valid and checked.fully_checked
    assert checked.violations == checked.warnings == []
    assert parsed == before
    assert validate_itinerary(parsed) == checked


@pytest.mark.parametrize("kind,expected", [
    ("overlap", "OVERLAP"), ("travel", "INSUFFICIENT_TRAVEL_TIME"),
    ("budget", "BUDGET_EXCEEDED"), ("closed", "CLOSED_LOCATION"),
    ("interval", "INVALID_INTERVAL"), ("bounds", "ACTIVITY_OUTSIDE_TRIP"),
])
def test_single_rule(payload, kind, expected):
    museum = payload["trip"]["activities"][1]
    if kind == "overlap":
        museum["start_time"] = "2026-11-16T09:30:00-06:00"
    elif kind == "travel":
        museum["start_time"] = "2026-11-16T10:10:00-06:00"
    elif kind == "budget":
        payload["trip"]["budget"] = "30.00"
    elif kind == "closed":
        payload["opening_hours"][1]["windows"] = []
    elif kind == "interval":
        museum["end_time"] = museum["start_time"]
    else:
        museum["end_time"] = "2026-11-17T00:00:01-06:00"
        payload["opening_hours"][1]["windows"][0]["end_time"] = museum["end_time"]
    checked = result(payload)
    assert not checked.is_valid
    assert codes(checked.violations) == [expected]
    assert all(issue.message for issue in checked.violations)
    expected_warnings = ["TRAVEL_CHECK_SKIPPED"] if kind in ("overlap", "interval") else []
    assert codes(checked.warnings) == expected_warnings
    if kind == "budget":
        assert "5.00 USD" in checked.violations[0].message
    if kind == "travel":
        assert "10m 0s" in checked.violations[0].message


@pytest.mark.parametrize("kind,expected", [
    ("moved", "FIXED_EVENT_MOVED"), ("missing", "FIXED_EVENT_MISSING"),
    ("location", "FIXED_EVENT_CHANGED"), ("flag", "FIXED_EVENT_CHANGED"),
    ("name", "FIXED_EVENT_CHANGED"), ("unexpected", "UNEXPECTED_FIXED_EVENT"),
])
def test_fixed_commitment_preservation(payload, kind, expected):
    event = payload["trip"]["activities"][0]
    if kind == "moved":
        event["start_time"] = "2026-11-16T08:30:00-06:00"
    elif kind == "missing":
        payload["trip"]["activities"].pop(0)
    elif kind == "location":
        event["location"]["name"] = "Wrong office"
    elif kind == "flag":
        event["fixed"] = False
    elif kind == "name":
        event["name"] = "Replacement"
    else:
        payload["trip"]["activities"][1]["fixed"] = True
    before = copy.deepcopy(payload)
    checked = result(payload)
    assert expected in codes(checked.violations)
    assert payload == before


@pytest.mark.parametrize("start,minutes,valid", [
    ("10:20:00", 20, True), ("10:19:59", 20, False),
    ("10:00:00", 20, False), ("10:00:00", 0, True),
])
def test_travel_boundaries(payload, start, minutes, valid):
    payload["trip"]["activities"][1]["start_time"] = f"2026-11-16T{start}-06:00"
    payload["travel_times"][0]["minutes"] = minutes
    checked = result(payload)
    assert checked.is_valid is valid
    assert "OVERLAP" not in codes(checked.violations)


def test_same_location_adjacent(payload):
    museum = payload["trip"]["activities"][1]
    museum["location"] = copy.deepcopy(payload["trip"]["activities"][0]["location"])
    museum["start_time"] = "2026-11-16T10:00:00-06:00"
    payload["travel_times"] = []
    payload["opening_hours"] = payload["opening_hours"][:1]
    assert result(payload).fully_checked
    assert result(payload).is_valid


@pytest.mark.parametrize("missing,expected", [
    ("travel", "MISSING_TRAVEL_TIME"), ("reverse", "MISSING_TRAVEL_TIME"),
    ("hours", "MISSING_OPENING_HOURS"), ("cost", "MISSING_COST_DATA"),
])
def test_unknown_does_not_mean_verified(payload, missing, expected):
    if missing == "travel":
        payload["travel_times"] = []
    elif missing == "reverse":
        payload["travel_times"][0].update(from_location_id="museum", to_location_id="office")
    elif missing == "hours":
        payload["opening_hours"].pop()
    else:
        payload["trip"]["activities"][1]["estimated_cost"] = None
    checked = result(payload)
    assert checked.is_valid and not checked.fully_checked
    assert codes(checked.warnings) == [expected]


def test_empty_and_exact_budget(payload):
    payload["trip"]["budget"] = "35.00"
    assert result(payload).is_valid
    payload["trip"]["activities"] = []
    payload["original_fixed_events"] = []
    payload["travel_times"] = payload["opening_hours"] = []
    checked = result(payload)
    assert checked.is_valid and checked.fully_checked


def test_decimal_budget(payload):
    payload["trip"]["budget"] = "0.30"
    payload["trip"]["activities"][0]["estimated_cost"] = "0.10"
    payload["trip"]["activities"][1]["estimated_cost"] = "0.20"
    assert result(payload).is_valid


@pytest.mark.parametrize("closing,valid", [("12:00:00", True), ("11:59:59", False)])
def test_opening_boundaries(payload, closing, valid):
    payload["opening_hours"][1]["windows"] = [{
        "start_time": "2026-11-16T10:30:00-06:00", "end_time": f"2026-11-16T{closing}-06:00",
    }]
    assert result(payload).is_valid is valid


@pytest.mark.parametrize("second_start,valid", [("11:00:00", True), ("11:01:00", False)])
def test_opening_union(payload, second_start, valid):
    payload["opening_hours"][1]["windows"] = [
        {"start_time": "2026-11-16T10:00:00-06:00", "end_time": "2026-11-16T11:00:00-06:00"},
        {"start_time": f"2026-11-16T{second_start}-06:00",
         "end_time": "2026-11-16T18:00:00-06:00"},
    ]
    assert result(payload).is_valid is valid


def test_nested_overlaps_and_accumulation(payload):
    a, b = payload["trip"]["activities"]
    a["end_time"] = "2026-11-16T13:00:00-06:00"
    payload["original_fixed_events"] = [copy.deepcopy(a)]
    c = copy.deepcopy(b)
    c.update(id="third", start_time="2026-11-16T11:00:00-06:00")
    payload["trip"]["activities"].append(c)
    checked = result(payload)
    overlaps = [v.activity_ids for v in checked.violations if v.code == "OVERLAP"]
    assert overlaps == [["interview", "museum"], ["interview", "third"], ["museum", "third"]]
    assert "BUDGET_EXCEEDED" in codes(checked.violations)
    payload["opening_hours"][1]["windows"] = []
    assert codes(result(payload).violations).count("CLOSED_LOCATION") == 2


def test_order_and_equivalent_offsets(payload):
    original = result(payload)
    payload["trip"]["activities"].reverse()
    for activity in payload["trip"]["activities"]:
        for field in ("start_time", "end_time"):
            activity[field] = datetime.fromisoformat(activity[field]).astimezone(
                timezone.utc).isoformat()
    assert result(payload) == original


@pytest.mark.parametrize("day,start,end", [
    ("2026-11-01", "01:15:00-05:00", "01:45:00-06:00"),
    ("2026-03-08", "01:30:00-06:00", "03:30:00-05:00"),
    ("2026-11-16", "23:00:00-06:00", "00:00:00-06:00"),
])
def test_timezone_and_upper_trip_bound(payload, day, start, end):
    activity = payload["trip"]["activities"][1]
    payload["trip"].update(start_date=day, end_date=day, activities=[activity])
    end_day = "2026-11-17" if day == "2026-11-16" else day
    activity.update(start_time=f"{day}T{start}", end_time=f"{end_day}T{end}")
    payload["original_fixed_events"] = []
    payload["travel_times"] = []
    payload["opening_hours"] = [{"location_id": "museum", "windows": [{
        "start_time": activity["start_time"], "end_time": activity["end_time"],
    }]}]
    assert result(payload).is_valid
