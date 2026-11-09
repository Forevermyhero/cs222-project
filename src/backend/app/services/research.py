"""Observable lookup records and source links; these are not an LLM's private reasoning.

The browser receives actual request/cache outcomes. Offline examples are labeled
separately, and a venue link never implies a ticket or booking was verified.
"""

from urllib.parse import urlsplit


def safe_link(value):
    """Only publish ordinary web links, without credentials or executable URL schemes."""
    if not isinstance(value, str) or any(c in value for c in ("\n", "\r", "\\")):
        return None
    try:
        parsed = urlsplit(value)
        if parsed.scheme in ("http", "https") and parsed.hostname and not parsed.username:
            return value
    except ValueError:
        pass
    return None


def map_link(location_id):
    parts = location_id.split(":")
    if len(parts) == 3 and parts[0] == "osm" and parts[1] in ("node", "way", "relation"):
        if parts[2].isdigit():
            return f"https://www.openstreetmap.org/{parts[1]}/{parts[2]}"
    return None


class ResearchLog:
    """One request's public activity log. Stable IDs let the UI update running rows."""

    def __init__(self, mode, observer=None):
        self.mode = mode
        self.observer = observer
        self.steps = []

    def record(self, title, status="completed", detail="", provider="Application",
               url=None, key=None, network_request=False):
        key = key or f"step-{len(self.steps) + 1}"
        record = {"id": key, "title": title, "status": status, "detail": detail,
                  "provider": provider, "url": safe_link(url), "data_mode": self.mode,
                  "network_request": network_request}
        previous = next((i for i, step in enumerate(self.steps) if step["id"] == key), None)
        if previous is None:
            self.steps.append(record)
        else:
            self.steps[previous] = record
        if self.observer:
            self.observer({"type": "progress", "step": record.copy()})
        return key

    def provider_event(self, event):
        return self.record(**event)


def source_cards(places, mode, known_hours):
    """Describe retrieved tags, including missing hours and unvisited website references."""
    cards = {}
    for place in places:
        location = place.location
        cards[location.id] = {
            "location_id": location.id, "name": location.name,
            "opening_hours": place.opening_expression,
            "hours_status": ("example" if mode == "demo" else
                             "usable" if location.id in known_hours else "unverified"),
            "source_url": map_link(location.id), "website_url": safe_link(place.website),
            "website_checked": False, "data_mode": mode,
        }
    return list(cards.values())


def preparation_items(activities, sources):
    """Suggestions only: no booking requirements, availability, or purchases are asserted."""
    by_location = {source["location_id"]: source for source in sources}
    items = []
    for activity in activities:
        source = by_location.get(activity.location.id, {})
        items.append({
            "activity_id": activity.id, "name": activity.name,
            "action": ("Confirm the time and address of your fixed commitment." if activity.fixed
                       else "Check current opening times and the ticket or reservation policy."),
            "url": source.get("website_url") or source.get("source_url"),
            "link_label": ("Venue website (not checked here)" if source.get("website_url")
                           else "OpenStreetMap listing"),
            "booking_required": None, "availability_checked": False,
        })
    return items
