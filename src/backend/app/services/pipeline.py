"""Orchestrate data -> generation -> independent validation with explicit provenance."""

from datetime import datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from ..models import Activity, OpeningHours, OpeningWindow, TravelTime, Trip, ValidationRequest
from ..time_utils import localize
from ..validator import utc, validate_itinerary
from .demo import canonical_destination, demo_places, demo_requested_ids
from .generation import heuristic_plan
from .opening_hours import expand_hours
from .providers import ProviderError, PublicDataClient, user_location
from .research import ResearchLog, preparation_items, source_cards


def plan_trip(request, client=None, progress=None):
    """Public planning entry point: observations are request-local and exportable.

    The same function powers ordinary JSON responses and the browser's live log.
    Research records describe tool actions, not a model's hidden chain of thought.
    """
    request = request.model_copy(update={"destination": canonical_destination(request.destination)})
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
    nearby_status = "not_queried"
    search_center = None
    if request.data_mode == "demo":
        if request.destination != "Chicago":
            raise ValueError("The bundled sample trip is Chicago. Select public map data "
                             "for another city, or load the Chicago example.")
        places = demo_places()
        requested_ids = demo_requested_ids(request.requested_places, places)
        nearby_status = "sample_not_queried"
        log.record("Load Chicago example places", status="example", provider="Local examples",
                   detail="Loaded four places written into the app: Art Institute, Field Museum, "
                   "Millennium Park and Riverwalk. Overpass and venue websites were not called.")
        notes.append("SAMPLE DATA: these four places are bundled examples. Their opening hours, "
                     "prices, reservation coordinates and 20-minute transfers are synthetic. "
                     "Activity times are calculated around your fixed reservations.")
        if requested_ids:
            notes.append("In this sample, Art Museum means the Art Institute of Chicago; "
                         "the remaining visits come from the bundled sample list.")
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
        requested_ids = {p.location.id for p in places}
        search_center = places[0].location if places else center
        if places:
            notes.append(f'Nearby search is centered on the first map match, '
                         f'"{search_center.name}". A broad term such as Art Museum is not '
                         "a confirmed venue choice; review the returned place name.")
        try:
            places += client.attractions(search_center)
            nearby_status = "completed"
        except ProviderError as exc:
            nearby_status = "failed"
            if not places:
                raise ProviderError("Overpass", str(exc) + " Add a specific venue name to "
                                    "plan that place even when nearby discovery is unavailable.")
            notes.append(str(exc) + " Continuing with only the explicitly resolved places; "
                         "no replacement nearby activities were invented.")
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
            location = user_location(original.location, 41.8807, -87.6269)
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
               detail=f"Kept {len(fixed)} reservations exactly as entered, including their "
               "times and locations. They are checked again after scheduling.")

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
               detail="Turn supplied hours such as Mo-Fr 09:00-17:00 into dated visit windows. "
               f"{len(hours)} locations have usable windows; every visit must fit entirely "
               "inside one. This step does not fetch websites; missing hours remain unknown.")

    # Resolve preferred demo places first without changing the provider's records.
    if request.data_mode == "demo":
        def preference_order(place):
            return place.location.id not in requested_ids, place.location.id
        places.sort(key=preference_order)
    planning_step = log.record("Arrange candidate activities", status="running",
                               provider="Rule-based planner",
                               detail="Try one-hour visits from 09:00 to 18:00 in 15-minute "
                               "steps. Keep reservations fixed and leave transfer time.")
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
    scheduled = {a.location.id: a for a in activities if not a.fixed}
    candidates = [{
        "location_id": p.location.id, "place_name": p.location.name,
        "activity_name": (scheduled[p.location.id].name if p.location.id in scheduled
                          else p.activity_title or f"Visit {p.location.name}"),
        "scheduled": p.location.id in scheduled,
        "reason": ("Chosen from the app's four Chicago sample places; not fetched online."
                   if request.data_mode == "demo" else
                   "Matched your requested place using Nominatim; review the first match."
                   if p.location.id in requested_ids else
                   "Found by Overpass within 3 km of the search center."),
    } for p in places]
    return {
        "request": validation_request.model_dump(mode="json"),
        "validation": result.model_dump(mode="json"),
        "fully_checked": result.fully_checked,
        "data_mode": request.data_mode, "planner": request.planner,
        "notes": notes, "unscheduled_places": unscheduled,
        "research_steps": log.steps, "sources": sources,
        "planning_summary": {
            "place_selection": ("Four bundled Chicago places; Art Museum selects the Art "
                                "Institute. These are sample suggestions, not web discoveries."
                                if request.data_mode == "demo" else
                                "Your resolved places first, followed by nearby map results. "
                                "Only places that fit the time constraints are scheduled."),
            "schedule_method": "Each flexible visit lasts 60 minutes. Try the earliest free "
                               "slot between 09:00 and 18:00, every 15 minutes. Keep reservations "
                               "fixed; check overlap, transfers, supplied hours and budget.",
            "nearby_search": nearby_status,
            "search_center": search_center.model_dump(mode="json") if search_center else None,
            "candidate_activities": candidates,
        },
        "preparation": preparation_items(validation_request.trip.activities, sources),
        "attributions": (["Synthetic Chicago demonstration fixtures"] if request.data_mode == "demo"
                         else ["Geocoding: Open-Meteo / GeoNames (CC BY 4.0)",
                               "Places: © OpenStreetMap contributors (ODbL), Nominatim/Overpass",
                               "Driving estimates: OSRM demo server / OpenStreetMap"]),
    }
