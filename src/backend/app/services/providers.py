"""No-key public data adapters. All network operations are explicit and bounded."""

import copy
import hashlib
import json
import math
import threading
import time
from dataclasses import dataclass, field
from decimal import Decimal
from urllib.parse import urlencode

import requests

from ..models import Location, TravelTime, valid_zone
from .research import safe_link

USER_AGENT = "ItineraryThatHoldsUp-CS222/0.1 (https://github.com/Forevermyhero/cs222-project)"


class ProviderError(Exception):
    def __init__(self, provider, message):
        self.provider = provider
        super().__init__(message)


@dataclass
class Place:
    location: Location
    opening_expression: str | None = None
    estimated_cost: Decimal | None = None
    website: str | None = None


@dataclass
class SharedProviderState:
    """Request-local observers share cache and rate limits, never each other's logs."""

    cache: dict = field(default_factory=dict)
    lock: object = field(default_factory=threading.Lock)
    nominatim_lock: object = field(default_factory=threading.Lock)
    last_nominatim: float = 0.0


class PublicDataClient:
    """Cache repeated public queries for 15 minutes; serialize Nominatim at <=1 request/s."""

    def __init__(self, session=None, state=None, observer=None):
        self.session = session or requests.Session()
        self.state = state or SharedProviderState()
        self.cache = self.state.cache
        self.lock = self.state.lock
        self.nominatim_lock = self.state.nominatim_lock
        self.observer = observer

    @property
    def last_nominatim(self):
        return self.state.last_nominatim

    @last_nominatim.setter
    def last_nominatim(self, value):
        self.state.last_nominatim = value

    def with_observer(self, observer):
        return PublicDataClient(self.session, self.state, observer)

    def event(self, **event):
        return self.observer(event) if self.observer else None

    def get_json(self, provider, url, params=None):
        """The HTTP boundary: record outcomes, use shared cache, preserve TLS verification."""
        public_url = url + ("?" + urlencode(params) if params else "")
        key = (url, json.dumps(params or {}, sort_keys=True))
        with self.lock:
            entry = self.cache.get(key)
            cache_hit = entry is not None and time.monotonic() - entry[0] < 900
            cached = copy.deepcopy(entry[1]) if cache_hit else None
        if cache_hit:
            self.event(title=f"Read {provider}", status="cached", provider=provider,
                       detail="Reused a cached response (at most 15 minutes old).",
                       url=public_url, network_request=False)
            return cached
        event_id = self.event(title=f"Query {provider}", status="running", provider=provider,
                              detail="Requesting source data.", url=public_url,
                              network_request=True)
        try:
            response = self.session.get(url, params=params, headers={"User-Agent": USER_AGENT},
                                        timeout=(5, 20))
            response.raise_for_status()
            if len(response.content) > 3_000_000:
                raise ProviderError(provider, "Provider response exceeded the size limit.")
            payload = response.json()
        except (requests.RequestException, ValueError, ProviderError):
            message = (f"{provider} is unavailable or returned invalid data. "
                       "Check network access or retry later; no live data was fabricated.")
            self.event(title=f"Query {provider}", status="failed", provider=provider,
                       detail=message, url=public_url, key=event_id, network_request=True)
            raise ProviderError(provider, message) from None
        with self.lock:
            if len(self.cache) >= 128:
                self.cache.pop(next(iter(self.cache)))
            self.cache[key] = (time.monotonic(), copy.deepcopy(payload))
        self.event(title=f"Query {provider}", status="completed", provider=provider,
                   detail="Received source JSON; relevant facts will be checked next.",
                   url=public_url, key=event_id, network_request=True)
        return payload

    def city(self, destination):
        """Resolve a city and its local timezone using Open-Meteo's public geocoder."""
        data = self.get_json("Open-Meteo geocoding",
                             "https://geocoding-api.open-meteo.com/v1/search",
                             {"name": destination, "count": 1, "language": "en", "format": "json"})
        try:
            city = data["results"][0]
            location = Location(id=f'city:{city["id"]}', name=city["name"],
                                latitude=city["latitude"], longitude=city["longitude"])
            return location, valid_zone(city["timezone"])
        except (KeyError, IndexError, TypeError, ValueError):
            raise ProviderError("Open-Meteo geocoding", "Destination was not found or malformed.")

    def find_place(self, name, destination):
        """Resolve one explicit address and read OSM tags; do not visit its website."""
        # No autocomplete or bulk geocoding; at most three requested places plus fixed events.
        with self.nominatim_lock:
            delay = 1.05 - (time.monotonic() - self.last_nominatim)
            if delay > 0:
                time.sleep(delay)
            try:
                rows = self.get_json("Nominatim", "https://nominatim.openstreetmap.org/search", {
                    "q": f"{name}, {destination}", "format": "jsonv2", "limit": 1,
                    "extratags": 1,
                })
            finally:
                self.last_nominatim = time.monotonic()
        try:
            row = rows[0]
            tags = row.get("extratags") or {}
            return Place(Location(id=f'osm:{row["osm_type"]}:{row["osm_id"]}', name=name,
                                  latitude=float(row["lat"]), longitude=float(row["lon"])),
                         tags.get("opening_hours"),
                         website=safe_link(tags.get("website") or tags.get("contact:website")))
        except (KeyError, IndexError, TypeError, ValueError):
            raise ProviderError("Nominatim", f'Could not resolve "{name}" in {destination}.')

    def attractions(self, center):
        """Request a small nearby attraction list, with source hours and website tags."""
        query = ('[out:json][timeout:15];nwr(around:3000,'
                 f'{center.latitude},{center.longitude})'
                 '["tourism"~"^(museum|attraction|gallery)$"];out center 16;')
        data = self.get_json("Overpass", "https://overpass-api.de/api/interpreter", {"data": query})
        places = []
        if not isinstance(data, dict) or not isinstance(data.get("elements"), list):
            raise ProviderError("Overpass", "Overpass returned no usable place data.")
        for row in data["elements"]:
            try:
                tags = row.get("tags", {})
                if not tags.get("name"):
                    continue
                point = row if "lat" in row else row["center"]
                places.append(Place(Location(id=f'osm:{row["type"]}:{row["id"]}', name=tags["name"],
                                             latitude=point["lat"], longitude=point["lon"]),
                                    tags.get("opening_hours"),
                                    website=safe_link(tags.get("website")
                                                      or tags.get("contact:website"))))
            except (KeyError, TypeError, ValueError):
                continue
        return sorted(places, key=lambda p: (p.location.name, p.location.id))[:6]

    def travel_matrix(self, locations):
        """Read directed driving estimates; null routes stay unknown, seconds round up."""
        unique = {p.id: p for p in locations}
        points = list(unique.values())
        if len(points) < 2:
            return []
        if len(points) > 20 or any(p.latitude is None for p in points):
            raise ProviderError("OSRM", "Routing requires coordinates for at most 20 locations.")
        coords = ";".join(f"{p.longitude},{p.latitude}" for p in points)
        data = self.get_json("OSRM", f"https://router.project-osrm.org/table/v1/driving/{coords}",
                             {"annotations": "duration"})
        try:
            durations = data["durations"]
            if data["code"] != "Ok" or len(durations) != len(points):
                raise ValueError("Invalid matrix")
            result = []
            for i, source in enumerate(points):
                if len(durations[i]) != len(points):
                    raise ValueError("Invalid matrix row")
                for j, target in enumerate(points):
                    seconds = durations[i][j]
                    if i != j and seconds is not None:
                        if isinstance(seconds, bool) or not math.isfinite(seconds) or seconds < 0:
                            raise ValueError("Invalid route duration")
                        result.append(TravelTime(from_location_id=source.id,
                                                 to_location_id=target.id,
                                                 minutes=math.ceil(seconds / 60)))
            return result
        except (KeyError, IndexError, TypeError, ValueError):
            raise ProviderError("OSRM", "OSRM returned an unusable duration matrix.")


def user_location(name, latitude, longitude):
    identity = hashlib.sha256(f"{name}|{latitude}|{longitude}".encode()).hexdigest()[:16]
    return Location(id=f"user:{identity}", name=name, latitude=latitude, longitude=longitude)
