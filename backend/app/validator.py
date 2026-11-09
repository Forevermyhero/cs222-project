"""Deterministic validation: no HTTP, clock, environment access, or input mutation."""

from datetime import datetime, time, timedelta, timezone
from decimal import Decimal
from itertools import combinations
from zoneinfo import ZoneInfo

from .models import ValidationRequest, ValidationResult, ValidationWarning, Violation


def utc(value):
    return value.astimezone(timezone.utc)


def validate_itinerary(request: ValidationRequest) -> ValidationResult:
    trip = request.trip
    violations, warnings = [], []

    def fail(code, ids, message):
        violations.append(Violation(code=code, activity_ids=ids, message=message))

    def warn(code, ids, message):
        warnings.append(ValidationWarning(code=code, activity_ids=ids, message=message))

    baseline = {a.id: a for a in request.original_fixed_events}
    candidates = {a.id: a for a in trip.activities}
    for event_id, original in baseline.items():
        candidate = candidates.get(event_id)
        if candidate is None:
            fail("FIXED_EVENT_MISSING", [event_id], f'Fixed event "{original.name}" is missing.')
            continue
        if (utc(candidate.start_time), utc(candidate.end_time)) != (
            utc(original.start_time), utc(original.end_time)
        ):
            fail("FIXED_EVENT_MOVED", [event_id],
                 f'Fixed event "{original.name}" must remain at '
                 f'{original.start_time.isoformat()}–{original.end_time.isoformat()}.')
        if (candidate.location != original.location or candidate.name != original.name
                or not candidate.fixed):
            fail("FIXED_EVENT_CHANGED", [event_id],
                 f'Fixed event "{original.name}" must keep its identity, location and fixed flag.')
    for activity in trip.activities:
        if activity.fixed and activity.id not in baseline:
            fail("UNEXPECTED_FIXED_EVENT", [activity.id],
                 f'"{activity.name}" is marked fixed but absent from the original commitments.')

    zone = ZoneInfo(trip.timezone)
    lower = utc(datetime.combine(trip.start_date, time.min, zone))
    upper = utc(datetime.combine(trip.end_date + timedelta(days=1), time.min, zone))
    positive = []
    for a in trip.activities:
        if utc(a.end_time) <= utc(a.start_time):
            fail("INVALID_INTERVAL", [a.id], f'"{a.name}": end must be after start.')
        else:
            positive.append(a)
            if utc(a.start_time) < lower or utc(a.end_time) > upper:
                fail("ACTIVITY_OUTSIDE_TRIP", [a.id],
                     f'"{a.name}" must fit within {trip.start_date}–{trip.end_date} '
                     f'in {trip.timezone}.')

    overlap = False
    for a, b in combinations(sorted(positive, key=lambda a: a.id), 2):
        if max(utc(a.start_time), utc(b.start_time)) < min(utc(a.end_time), utc(b.end_time)):
            overlap = True
            fail("OVERLAP", [a.id, b.id], f'"{a.name}" overlaps "{b.name}".')

    if len(positive) != len(trip.activities) or overlap:
        warn("TRAVEL_CHECK_SKIPPED", sorted(candidates),
             "Resolve invalid or overlapping activity intervals before checking travel.")
    else:
        facts = {(t.from_location_id, t.to_location_id): t.minutes for t in request.travel_times}
        ordered = sorted(positive, key=lambda a: (utc(a.start_time), utc(a.end_time), a.id))
        for a, b in zip(ordered, ordered[1:]):
            if a.location.id == b.location.id:
                continue
            required = facts.get((a.location.id, b.location.id))
            if required is None:
                warn("MISSING_TRAVEL_TIME", [a.id, b.id],
                     f'No directed travel estimate from "{a.location.name}" '
                     f'to "{b.location.name}"; this leg is unverified.')
                continue
            gap = utc(b.start_time) - utc(a.end_time)
            if gap < timedelta(minutes=required):
                seconds = int(gap.total_seconds())
                fail("INSUFFICIENT_TRAVEL_TIME", [a.id, b.id],
                     f'"{a.name}" to "{b.name}" allows {seconds // 60}m {seconds % 60}s; '
                     f'{required} minutes are required.')

    if trip.budget is not None:
        total = sum((a.estimated_cost or Decimal("0.00") for a in trip.activities), Decimal("0.00"))
        unknown = sorted(a.id for a in trip.activities if a.estimated_cost is None)
        if unknown:
            warn("MISSING_COST_DATA", unknown,
                 "Some activity costs are unknown; the full budget cannot be verified.")
        if total > trip.budget:
            fail("BUDGET_EXCEEDED", sorted(candidates),
                 f'Total {total:.2f} USD exceeds budget {trip.budget:.2f} USD '
                 f'by {total - trip.budget:.2f} USD (supplied activity estimates only).')

    opening = {h.location_id: merge_windows(h.windows) for h in request.opening_hours}
    missing = {}
    for a in positive:
        windows = opening.get(a.location.id)
        if windows is None:
            missing.setdefault(a.location.id, []).append(a)
        elif not any(start <= utc(a.start_time) and utc(a.end_time) <= end
                     for start, end in windows):
            fail("CLOSED_LOCATION", [a.id],
                 f'"{a.location.name}" does not cover "{a.name}" at '
                 f'{a.start_time.isoformat()}–{a.end_time.isoformat()} in known opening windows.')
    for location_id, activities in sorted(missing.items()):
        warn("MISSING_OPENING_HOURS", sorted(a.id for a in activities),
             f'No usable hours for "{activities[0].location.name}"; visits are unverified.')

    def key(issue):
        return issue.code, tuple(issue.activity_ids)
    return ValidationResult(is_valid=not violations, violations=sorted(violations, key=key),
                            warnings=sorted(warnings, key=key))


def merge_windows(windows):
    merged = []
    for start, end in sorted((utc(w.start_time), utc(w.end_time)) for w in windows):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
        else:
            merged.append((start, end))
    return merged
