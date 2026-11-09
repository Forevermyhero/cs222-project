"""Orchestrate data -> generation -> independent validation with explicit provenance."""

from datetime import datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from ..models import Activity, OpeningHours, OpeningWindow, TravelTime, Trip, ValidationRequest
from ..time_utils import localize
from ..validator import utc, validate_itinerary
from .demo import demo_places
from .generation import heuristic_plan
from .opening_hours import expand_hours
from .providers import ProviderError, PublicDataClient, user_location
from .research import ResearchLog, preparation_items, source_cards


def plan_trip(request, client=None, progress=None):
    """Public planning entry point: observations are request-local and exportable.

    The same function powers ordinary JSON responses and the browser's live log.
    Research records describe tool actions, not a model's hidden chain of thought.
    """
    log = ResearchLog(request.data_mode, progress)
    client = client or PublicDataClient()
    if hasattr(client, "with_observer"):
        client = client.with_observer(log.provider_event)
    try:
        return _plan_trip(request, client, log)
    except (ProviderError, ValueError) as error:
        log.record("Planning stopped", status="failed", detail=str(error),
                   provider=getattr(error, "provider", "Input checks"))
        error.research_steps = log.steps
        raise


def _plan_trip(request, client, log):
    log.record("Read your trip details", detail=f"{request.destination}; "
               f"{len(request.fixed_events)} original fixed commitments.", provider="Your inputs")
    notes = []
    zone = ZoneInfo(request.timezone)
    lower = localize(datetime.combine(request.start_date, time.min), zone)
    upper = localize(datetime.combine(request.end_date + timedelta(days=1), time.min), zone)
    opening_zone = request.timezone
    if request.data_mode == "demo":
        if request.destination.casefold() != "chicago":
            raise ValueError("Demo mode contains only Chicago. Choose live data for other cities.")
        places = demo_places()
        log.record("Load Chicago example places", status="example", provider="Local examples",
                   detail="Loaded four bundled places. No website was contacted.")
        notes.append("DEMO DATA: opening hours, prices, event coordinates and travel times are "
                     "synthetic fixtures. The heuristic planner does not call an LLM.")
        for name in request.requested_places:
            if not any(name.casefold() in p.location.name.casefold() for p in places):
                raise ValueError(f'Demo data does not contain requested place "{name}".')
    else:
        center, city_zone = client.city(request.destination)
        log.record("Resolve the destination", provider="Open-Meteo geocoding",
                   detail=f"Resolved {center.name}; local timezone {city_zone}.")
        opening_zone = city_zone
        if city_zone != request.timezone:
            notes.append(f"Destination timezone is {city_zone}; the trip explicitly uses "
                         f"{request.timezone}. All scheduled times use the trip timezone.")
        # Explicit requests are prioritized; no public bulk/autocomplete geocoding.
        places = [client.find_place(name, request.destination) for name in request.requested_places]
        try:
            places += client.attractions(center)
        except ProviderError as exc:
            if not places:
                raise
            notes.append(str(exc))
        places = list({p.location.id: p for p in places}.values())[:8]
        if not places:
            raise ProviderError("OpenStreetMap", "No usable activities were found near this city.")
        notes.append("Live public map data can be incomplete. OSRM durations are driving estimates "
                     "without live traffic; they are not walking or transit estimates.")

    fixed = []
    fixed_places = []
    for original in request.fixed_events:
        if original.latitude is not None:
            location = user_location(original.location, original.latitude, original.longitude)
        elif request.data_mode == "demo":
            location = user_location(original.location, 41.8810, -87.6290)
        else:
            resolved = client.find_place(original.location, request.destination)
            location = resolved.location
            fixed_places.append(resolved)
        start, end = localize(original.start_time, zone), localize(original.end_time, zone)
        if utc(end) <= utc(start):
            raise ValueError("Fixed events need a positive interval before planning.")
        if utc(start) < utc(lower) or utc(end) > utc(upper):
            raise ValueError("Original fixed events must lie within the trip dates.")
        cost = Decimal("0.00") if request.data_mode == "demo" else None
        fixed.append(Activity(id=original.id, name=original.name, location=location,
                              start_time=start, end_time=end,
                              estimated_cost=cost,
                              fixed=True, priority="high"))
    log.record("Keep the original commitments", provider="Your inputs",
               detail=f"Retained {len(fixed)} fixed events as a separate validation baseline.")

    locations = [p.location for p in places] + [a.location for a in fixed]
    locations = list({p.id: p for p in locations}.values())
    if request.data_mode == "demo":
        travel = [TravelTime(from_location_id=a.id, to_location_id=b.id, minutes=20)
                  for a in locations for b in locations if a.id != b.id]
        log.record("Load example travel estimates", status="example", provider="Local examples",
                   detail="Loaded synthetic 20-minute transfers. No routing service was queried.")
    else:
        try:
            travel = client.travel_matrix(locations)
        except ProviderError as exc:
            travel = []
            notes.append(str(exc) + " Travel checks will be marked incomplete.")

    hours_by_id = {}
    city_zone = ZoneInfo(opening_zone)
    opening_start = lower.astimezone(city_zone).date()
    opening_end = (utc(upper) - timedelta(microseconds=1)).astimezone(city_zone).date()
    for place in places + fixed_places:
        expanded = expand_hours(place.location.id, place.opening_expression,
                                opening_start, opening_end, opening_zone)
        if expanded is not None:
            hours_by_id[place.location.id] = expanded
    hours = list(hours_by_id.values())
    # A private meeting's hours are not inferred from the AI or an unrelated attraction.
    # Demo hours for its synthetic office are explicit fixtures.
    if request.data_mode == "demo":
        for location_id in sorted({a.location.id for a in fixed} - {h.location_id for h in hours}):
            hours.append(OpeningHours(location_id=location_id, windows=[OpeningWindow(
                start_time=localize(datetime.combine(request.start_date, time.min), zone),
                end_time=localize(datetime.combine(request.end_date + timedelta(days=1),
                                                   time.min), zone),
            )]))
    log.record("Prepare opening-hour checks", provider="Opening-hours parser",
               status="example" if request.data_mode == "demo" else "completed",
               detail=f"{len(hours)} locations have usable windows. Missing or unsupported "
               "expressions remain unverified.")

    # Resolve preferred demo places first without changing the provider's records.
    if request.data_mode == "demo":
        def preference_order(place):
            requested = any(name.casefold() in place.location.name.casefold()
                            for name in request.requested_places)
            return not requested, place.location.id
        places.sort(key=preference_order)
    planning_step = log.record("Arrange candidate activities", status="running",
                               provider="Rule-based planner",
                               detail="Looking for slots around fixed events; no LLM is connected.")
    activities, unscheduled = heuristic_plan(request, fixed, places, travel, hours)
    log.record("Arrange candidate activities", provider="Rule-based planner", key=planning_step,
               detail=f"Proposed {len(activities)} activities; {len(unscheduled)} did not fit.")
    for name in unscheduled:
        notes.append(f'Could not fit "{name}" around the constraints; it was not scheduled.')

    used = {a.location.id for a in activities + fixed}
    validation_request = ValidationRequest(
        trip=Trip(destination=request.destination, start_date=request.start_date,
                  end_date=request.end_date, timezone=request.timezone, budget=request.budget,
                  preferences=request.preferences,
                  activities=sorted(activities, key=lambda a: (utc(a.start_time), a.id))),
        original_fixed_events=fixed,
        travel_times=[t for t in travel if t.from_location_id in used and t.to_location_id in used],
        opening_hours=[h for h in hours if h.location_id in used],
    )
    checking_step = log.record("Check the schedule", status="running", provider="Python validator",
                               detail="Checking fixed events, overlap, travel and opening windows.")
    result = validate_itinerary(validation_request)
    log.record("Check the schedule", provider="Python validator", key=checking_step,
               detail=f"{len(result.violations)} violations; {len(result.warnings)} warnings.")
    sources = source_cards(places + fixed_places, request.data_mode, hours_by_id)
    return {
        "request": validation_request.model_dump(mode="json"),
        "validation": result.model_dump(mode="json"),
        "fully_checked": result.fully_checked,
        "data_mode": request.data_mode, "planner": request.planner,
        "notes": notes, "unscheduled_places": unscheduled,
        "research_steps": log.steps, "sources": sources,
        "preparation": preparation_items(validation_request.trip.activities, sources),
        "attributions": (["Synthetic Chicago demonstration fixtures"] if request.data_mode == "demo"
                         else ["Geocoding: Open-Meteo / GeoNames (CC BY 4.0)",
                               "Places: © OpenStreetMap contributors (ODbL), Nominatim/Overpass",
                               "Driving estimates: OSRM demo server / OpenStreetMap"]),
    }
