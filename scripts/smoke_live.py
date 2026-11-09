"""Explicitly contact public services: python -m scripts.smoke_live."""

import argparse
import json

from backend.app.models import PlanRequest
from backend.app.services.pipeline import plan_trip
from backend.app.services.providers import ProviderError, PublicDataClient


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination", default="Chicago")
    parser.add_argument("--start-date", default="2026-11-16")
    args = parser.parse_args()
    client = PublicDataClient()
    report = {"kind": "live public API smoke", "destination": args.destination}
    try:
        center, zone = client.city(args.destination)
        report["geocoding"] = center.model_dump(mode="json")
        places = client.attractions(center)
        if not places:
            raise ProviderError("Overpass", "No named attractions were returned.")
        # One explicit query, not autocomplete or bulk lookup.
        resolved = client.find_place(places[0].location.name, args.destination)
        report["nominatim"] = resolved.location.model_dump(mode="json")
        route_places = list({p.location.id: p.location for p in places[:2]}.values())
        if len(route_places) < 2:
            raise ProviderError("OSRM", "Two distinct places are needed for the smoke check.")
        travel = client.travel_matrix(route_places)
        if not travel:
            raise ProviderError("OSRM", "No usable directed routes were returned.")
        report["directed_routes"] = len(travel)
        candidate = plan_trip(PlanRequest(
            destination=args.destination, start_date=args.start_date, end_date=args.start_date,
            timezone=zone, data_mode="live", planner="heuristic",
        ), client=client)
        report.update(passed=True, activity_count=len(candidate["request"]["trip"]["activities"]),
                      validation=candidate["validation"],
                      notes=candidate["notes"], fully_checked=candidate["fully_checked"])
    except (ProviderError, ValueError) as error:
        report.update(passed=False, error=str(error), provider=getattr(error, "provider", None))
    print(json.dumps(report, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
