"""Conservative OSM subset. Unsupported expressions remain unknown, never guessed."""

import re
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from ..models import OpeningHours, OpeningWindow
from ..time_utils import localize

DAYS = ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"]
DAY = r"(?:Mo|Tu|We|Th|Fr|Sa|Su)"
RULE = re.compile(rf"(?:(?P<days>{DAY}(?:[-,]{DAY})*)\s+)?"
                  r"(?P<times>off|closed|\d{2}:\d{2}-\d{2}:\d{2}"
                  r"(?:,\d{2}:\d{2}-\d{2}:\d{2})*)")


def expand_hours(location_id, expression, start_date, end_date, timezone_name):
    """Return None for missing/unsupported/ambiguous data; [] explicitly means closed."""
    if not expression or not isinstance(expression, str):
        return None
    zone = ZoneInfo(timezone_name)
    expression = expression.strip()
    if expression == "24/7":
        return OpeningHours(location_id=location_id, windows=[OpeningWindow(
            start_time=localize(datetime.combine(start_date, time.min), zone),
            end_time=localize(datetime.combine(end_date + timedelta(days=1), time.min), zone),
        )])
    weekly = {day: [] for day in range(7)}
    try:
        for text in expression.split(";"):
            match = RULE.fullmatch(text.strip())
            if not match:
                return None
            days = set(range(7)) if match["days"] is None else weekdays(match["days"])
            spans = []
            if match["times"] not in ("off", "closed"):
                for span in match["times"].split(","):
                    start, end = [clock_minutes(t) for t in span.split("-")]
                    if start == 1440 or start == end:
                        return None
                    spans.append((start, end))
            for day in days:
                weekly[day] = spans
        windows = []
        # Include the previous day to preserve overnight openings into the first trip day.
        current = start_date - timedelta(days=1)
        while current <= end_date:
            midnight = datetime.combine(current, time.min)
            for start, end in weekly[current.weekday()]:
                if end <= start:
                    end += 1440
                windows.append(OpeningWindow(
                    start_time=localize(midnight + timedelta(minutes=start), zone),
                    end_time=localize(midnight + timedelta(minutes=end), zone),
                ))
            current += timedelta(days=1)
        return OpeningHours(location_id=location_id, windows=windows)
    except ValueError:
        return None


def weekdays(text):
    result = set()
    for item in text.split(","):
        if "-" not in item:
            result.add(DAYS.index(item))
        else:
            first, last = [DAYS.index(v) for v in item.split("-")]
            while first != last:
                result.add(first)
                first = (first + 1) % 7
            result.add(last)
    return result


def clock_minutes(text):
    hour, minute = [int(v) for v in text.split(":")]
    if hour > 24 or minute > 59 or (hour == 24 and minute):
        raise ValueError("Invalid clock time.")
    return hour * 60 + minute
