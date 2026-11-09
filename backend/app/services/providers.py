"""No-key public data adapters. All network operations are explicit and bounded."""

import copy
import hashlib
import json
import math
import threading
import time
from dataclasses import dataclass
from decimal import Decimal

import requests

from ..models import Location, TravelTime, valid_zone

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


class PublicDataClient:
    """Cache repeated public queries for 15 minutes; serialize Nominatim at <=1 request/s."""

    def __init__(self, session=None):
        self.session = session or requests.Session()
        self.cache = {}
        self.lock = threading.Lock()
        self.nominatim_lock = threading.Lock()
        self.last_nominatim = 0.0

    def get_json(self, provider, url, params=None):
        key = (url, json.dumps(params or {}, sort_keys=True))
        with self.lock:
            entry = self.cache.get(key)
            if entry and time.monotonic() - entry[0] < 900:
                return copy.deepcopy(entry[1])
        try:
            response = self.session.get(url, params=params, headers={"User-Agent": USER_AGENT},
                                        timeout=(5, 20))
            response.raise_for_status()
            if len(response.content) > 3_000_000:
                raise ProviderError(provider, "Provider response exceeded the size limit.")
            payload = response.json()
        except (requests.RequestException, ValueError):
            raise ProviderError(provider, f"{provider} is unavailable or returned invalid data. "
                                "Check network access or retry later; no live data was fabricated.")
        with self.lock:
            if len(self.cache) >= 128:
                self.cache.pop(next(iter(self.cache)))
            self.cache[key] = (time.monotonic(), copy.deepcopy(payload))
        return payload

    def city(self, destination):
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
            return Place(Location(id=f'osm:{row["osm_type"]}:{row["osm_id"]}', name=name,
                                  latitude=float(row["lat"]), longitude=float(row["lon"])),
                         (row.get("extratags") or {}).get("opening_hours"))
        except (KeyError, IndexError, TypeError, ValueError):
            raise ProviderError("Nominatim", f'Could not resolve "{name}" in {destination}.')

    def attractions(self, center):
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
                                    tags.get("opening_hours")))
            except (KeyError, TypeError, ValueError):
                continue
        return sorted(places, key=lambda p: (p.location.name, p.location.id))[:6]

    def travel_matrix(self, locations):
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
