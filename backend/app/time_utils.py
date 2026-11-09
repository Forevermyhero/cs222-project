"""Explicit local-time conversion for the form and the limited opening-hours parser."""

from datetime import datetime, timezone
from zoneinfo import ZoneInfo


def localize(value: datetime, zone: ZoneInfo) -> datetime:
    if value.tzinfo is not None:
        return value.astimezone(zone)
    candidates = []
    for fold in (0, 1):
        candidate = value.replace(tzinfo=zone, fold=fold)
        back = candidate.astimezone(timezone.utc).astimezone(zone).replace(tzinfo=None)
        if back == value and candidate.utcoffset() not in [v.utcoffset() for v in candidates]:
            candidates.append(candidate)
    if len(candidates) != 1:
        raise ValueError("This local time is ambiguous or nonexistent due to a timezone change. "
                         "Supply an explicit UTC offset using the JSON API.")
    return candidates[0]
