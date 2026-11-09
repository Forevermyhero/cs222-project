"""Strict request contracts. Scheduling failures belong in validator.py."""

import re
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Annotated, Literal, Self
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import (
    AfterValidator, AwareDatetime, BaseModel, BeforeValidator, ConfigDict,
    Field, StrictBool, StrictInt, model_validator,
)


def temporal_input(value):
    if not isinstance(value, (str, date, datetime)):
        raise ValueError("Use an ISO date/time string, not a numeric timestamp.")
    return value


def valid_zone(value: str) -> str:
    try:
        ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError):
        raise ValueError("Use an IANA timezone such as America/Chicago.") from None
    return value


def date_input(value):
    if type(value) is date:
        return value
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ValueError("Use an ISO calendar date (YYYY-MM-DD).")
    return value


Text = Annotated[str, Field(min_length=1, max_length=200)]
Timestamp = Annotated[AwareDatetime, BeforeValidator(temporal_input)]
ISODate = Annotated[date, BeforeValidator(date_input)]
Zone = Annotated[str, AfterValidator(valid_zone)]
Money = Annotated[Decimal, Field(ge=0, max_digits=12, decimal_places=2, allow_inf_nan=False)]
Priority = Literal["low", "medium", "high"]


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, validate_default=True)


class Location(Model):
    id: Text
    name: Text
    latitude: float | None = Field(default=None, ge=-90, le=90, allow_inf_nan=False)
    longitude: float | None = Field(default=None, ge=-180, le=180, allow_inf_nan=False)

    @model_validator(mode="after")
    def coordinate_pair(self) -> Self:
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("Supply both latitude and longitude, or neither.")
        return self


class Activity(Model):
    id: Text
    name: Text
    location: Location
    start_time: Timestamp
    end_time: Timestamp
    estimated_cost: Money | None = None
    priority: Priority = "medium"
    fixed: StrictBool = False


class Trip(Model):
    destination: Text
    start_date: ISODate
    end_date: ISODate
    timezone: Zone
    budget: Money | None = None
    currency: Literal["USD"] = "USD"
    preferences: list[Text] = Field(default_factory=list, max_length=20)
    activities: list[Activity] = Field(max_length=100)

    @model_validator(mode="after")
    def dates_and_ids(self) -> Self:
        check_dates(self.start_date, self.end_date)
        unique([a.id for a in self.activities], "activity ID")
        return self


class TravelTime(Model):
    from_location_id: Text
    to_location_id: Text
    minutes: StrictInt = Field(ge=0, le=10080)

    @model_validator(mode="after")
    def no_self_pair(self) -> Self:
        if self.from_location_id == self.to_location_id:
            raise ValueError("Same-location travel is implicitly zero; omit self-pair facts.")
        return self


class OpeningWindow(Model):
    start_time: Timestamp
    end_time: Timestamp

    @model_validator(mode="after")
    def positive(self) -> Self:
        from datetime import timezone
        if self.end_time.astimezone(timezone.utc) <= self.start_time.astimezone(timezone.utc):
            raise ValueError("Opening windows must have positive duration.")
        return self


class OpeningHours(Model):
    location_id: Text
    windows: list[OpeningWindow] = Field(max_length=200)


class ValidationRequest(Model):
    trip: Trip
    # A separate authoritative baseline is required, including [] when there are no fixed events.
    original_fixed_events: list[Activity] = Field(max_length=30)
    travel_times: list[TravelTime] = Field(default_factory=list, max_length=1000)
    opening_hours: list[OpeningHours] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def unambiguous_facts(self) -> Self:
        unique([a.id for a in self.original_fixed_events], "original fixed-event ID")
        if any(not a.fixed for a in self.original_fixed_events):
            raise ValueError("Original fixed events must have fixed=true.")
        locations = {a.location.id for a in self.trip.activities + self.original_fixed_events}
        pairs = [(t.from_location_id, t.to_location_id) for t in self.travel_times]
        unique(pairs, "travel pair")
        unique([h.location_id for h in self.opening_hours], "opening-hours location")
        references = {h.location_id for h in self.opening_hours}
        references |= {v for t in self.travel_times for v in
                       (t.from_location_id, t.to_location_id)}
        if not references <= locations:
            raise ValueError("External facts reference an unknown location.")
        return self


ViolationCode = Literal[
    "INVALID_INTERVAL", "ACTIVITY_OUTSIDE_TRIP", "OVERLAP", "INSUFFICIENT_TRAVEL_TIME",
    "BUDGET_EXCEEDED", "CLOSED_LOCATION", "FIXED_EVENT_MISSING", "FIXED_EVENT_MOVED",
    "FIXED_EVENT_CHANGED", "UNEXPECTED_FIXED_EVENT",
]
WarningCode = Literal[
    "MISSING_TRAVEL_TIME", "MISSING_OPENING_HOURS", "TRAVEL_CHECK_SKIPPED", "MISSING_COST_DATA",
]


class Violation(Model):
    code: ViolationCode
    activity_ids: list[str]
    message: str


class ValidationWarning(Model):
    code: WarningCode
    activity_ids: list[str]
    message: str


class ValidationResult(Model):
    is_valid: bool
    violations: list[Violation]
    warnings: list[ValidationWarning]

    @property
    def fully_checked(self) -> bool:
        return not self.warnings


class FixedEventInput(Model):
    id: Text
    name: Text
    location: Text
    # Form timestamps may be local, with the trip's explicit IANA zone.
    start_time: Annotated[datetime, BeforeValidator(temporal_input)]
    end_time: Annotated[datetime, BeforeValidator(temporal_input)]
    latitude: float | None = Field(default=None, ge=-90, le=90, allow_inf_nan=False)
    longitude: float | None = Field(default=None, ge=-180, le=180, allow_inf_nan=False)

    @model_validator(mode="after")
    def pair(self) -> Self:
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("Supply both event coordinates or neither.")
        return self


class PlanRequest(Model):
    destination: Text
    start_date: ISODate
    end_date: ISODate
    timezone: Zone = "America/Chicago"
    preferences: list[Text] = Field(default_factory=list, max_length=20)
    requested_places: list[Text] = Field(default_factory=list, max_length=3)
    fixed_events: list[FixedEventInput] = Field(default_factory=list, max_length=10)
    budget: Money | None = None
    data_mode: Literal["demo", "live"] = "demo"
    planner: Literal["heuristic", "openai"] = "heuristic"

    @model_validator(mode="after")
    def coherent(self) -> Self:
        check_dates(self.start_date, self.end_date)
        unique([a.id for a in self.fixed_events], "fixed-event ID")
        return self


def unique(values, label):
    if len(values) != len(set(values)):
        raise ValueError(f"Duplicate {label}.")


def check_dates(start: date, end: date):
    if end < start:
        raise ValueError("end_date must be on or after start_date.")
    if end == date.max or start.year < 1900 or end.year > 2100:
        raise ValueError("Prototype dates must be between 1900 and 2100.")
    if end - start >= timedelta(days=14):
        raise ValueError("The prototype supports trips of at most 14 days.")
