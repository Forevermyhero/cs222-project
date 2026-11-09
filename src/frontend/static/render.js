/* Display only: source records, schedules, preparation suggestions and validation.
   All external/user text uses textContent. URLs must be ordinary HTTP(S) links. */
export const $ = (id) => document.getElementById(id);
export function element(tag, text, className) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (className) node.className = className;
  return node;
}

function link(url, label) {
  try {
    const parsed = new URL(url);
    if (!["https:", "http:"].includes(parsed.protocol) || parsed.username) return null;
    const anchor = element("a", label || parsed.hostname, "source-link");
    anchor.href = parsed.href;
    anchor.target = "_blank";
    anchor.rel = "noopener noreferrer";
    return anchor;
  } catch { return null; }
}

const rows = new Map();
const records = new Map();
let selectedStep = null;
let following = true;
const stepLabels = { completed: "Done", cached: "Done · cached", running: "In progress", example: "Done · sample data", failed: "Failed", stopped: "Stopped" };

// Review only changes the selected record. It never repeats a provider request.
function updateStepViewer() {
  const ids = [...records.keys()];
  if (following) selectedStep = ids.at(-1) || null;
  const index = ids.indexOf(selectedStep);
  const step = records.get(selectedStep);
  $("step-position").textContent = `${index + 1} / ${ids.length}`;
  $("step-previous").disabled = index <= 0;
  $("step-next").disabled = index < 0 || index === ids.length - 1;
  $("step-follow").setAttribute("aria-pressed", String(following));
  $("step-title").textContent = step?.title || "Waiting for the first step";
  $("step-meta").textContent = step ? `${step.provider} · ${stepLabels[step.status] || step.status} · ${step.network_request ? "Network request" : step.status === "cached" ? "Cached response" : "Local step"}` : "";
  $("step-detail").textContent = step?.detail || "";
  $("step-source").replaceChildren();
  const source = link(step?.url, step?.url);
  if (source) $("step-source").append(source);
  for (const [id, row] of rows) {
    row.classList.toggle("selected-step", id === selectedStep);
    row.querySelector("button").setAttribute("aria-current", id === selectedStep ? "step" : "false");
  }
}

export function reviewStep(direction) {
  const ids = [...records.keys()];
  const index = ids.indexOf(selectedStep);
  if (index < 0) return;
  following = false;
  selectedStep = ids[Math.max(0, Math.min(ids.length - 1, index + direction))];
  updateStepViewer();
}

export function followResearch() {
  following = true;
  updateStepViewer();
}

export function resetResearch(mode) {
  rows.clear(); records.clear();
  selectedStep = null; following = true;
  $("research-steps").replaceChildren();
  $("source-cards").replaceChildren();
  $("research-panel").hidden = false;
  $("research-panel").open = true;
  $("research-mode").textContent = mode === "demo" ? "Example walkthrough" : "Live source requests";
  $("research-disclaimer").textContent = mode === "demo"
    ? "Offline sample. No live websites are visited. Steps marked Done · sample data are finished; they read bundled examples instead of querying maps."
    : "These are the backend's actual requests. Cached results and failed lookups are labeled.";
  $("research-count").textContent = "Starting";
  updateStepViewer();
}

export function renderStep(step) {
  let row = rows.get(step.id);
  if (!row) {
    row = element("li");
    rows.set(step.id, row);
    $("research-steps").append(row);
  }
  records.set(step.id, step);
  row.className = `research-step step-${step.status}`;
  const body = element("div", undefined, "step-body");
  const top = element("div", undefined, "step-heading");
  const select = element("button", step.title, "step-select");
  select.type = "button";
  select.addEventListener("click", () => {
    selectedStep = step.id; following = false; updateStepViewer();
  });
  top.append(select, element("span", stepLabels[step.status] || step.status, "step-status"));
  body.append(top, element("p", step.detail));
  const source = link(step.url, `${step.provider} · view source response`);
  if (source) body.append(source);
  row.replaceChildren(element("span", undefined, "step-dot"), body);
  const finished = [...records.values()].filter((s) => ["completed", "cached", "example", "failed", "stopped"].includes(s.status)).length;
  const failed = [...records.values()].filter((s) => s.status === "failed").length;
  $("research-count").textContent = `${finished}/${rows.size} finished${failed ? ` · ${failed} failed` : ""}`;
  updateStepViewer();
}

export function stopResearch() {
  for (const step of records.values()) {
    if (step.status === "running") renderStep({ ...step, status: "stopped", detail: "The request stopped before its outcome was confirmed." });
  }
}

export function renderValidation(validation, mode) {
  const label = !validation.is_valid ? "Needs changes" : validation.warnings.length
    ? "Partially checked" : mode === "demo" ? "Example checks passed" : "Known checks passed";
  $("validity").textContent = label;
  $("validity").className = `pill ${!validation.is_valid ? "invalid" : validation.warnings.length ? "partial" : "valid"}`;
  $("issues").replaceChildren();
  for (const [items, kind] of [[validation.violations, ""], [validation.warnings, "warning"]]) {
    items.forEach((issue) => {
      const card = element("div", undefined, `issue ${kind}`);
      card.append(element("strong", issue.code.replaceAll("_", " ")), element("span", issue.message));
      $("issues").append(card);
    });
  }
  if (!validation.violations.length && !validation.warnings.length) {
    $("issues").append(element("div", "All constraints passed against the supplied facts.", "issue ok"));
  }
}

function renderSources(sources) {
  $("source-cards").replaceChildren();
  sources.forEach((source) => {
    const card = element("article", undefined, "source-card");
    const label = source.data_mode === "demo" ? "Sample hours · bundled" : source.hours_status === "usable" ? "Map-reported hours" : "Hours unverified";
    card.append(element("p", label, "eyebrow"), element("h4", source.name),
      element("p", source.opening_hours || "No usable opening-hour data was supplied."));
    const map = link(source.source_url, "View map record");
    const venue = link(source.website_url, "Venue website · not checked here");
    if (map) card.append(map);
    if (venue) card.append(venue);
    if (source.data_mode === "demo") card.append(element("small", "This place and its hours came from the app's sample list. Overpass and these reference links were not queried."));
    $("source-cards").append(card);
  });
}

function renderPreparation(items) {
  $("preparation-list").replaceChildren();
  items.forEach((item, index) => {
    const row = element("li");
    const body = element("div");
    body.append(element("strong", item.name), element("p", item.action));
    const action = link(item.url, item.link_label);
    if (action) body.append(action);
    row.append(element("span", String(index + 1).padStart(2, "0"), "prep-number"), body);
    $("preparation-list").append(row);
  });
}

export function renderResult(result) {
  $("empty-state").hidden = true;
  $("result-content").hidden = false;
  $("trip-heading").textContent = `Your ${result.request.trip.destination} itinerary`;
  $("result-mode").textContent = result.data_mode === "demo" ? "Sample places · automatically scheduled" : "Public map places · automatically scheduled";
  const summary = result.planning_summary;
  $("selection-summary").textContent = summary?.place_selection || "See the source records for where the candidate places came from.";
  $("schedule-method").textContent = summary?.schedule_method || "Visits are fitted around your fixed reservations and checked independently.";
  $("nearby-summary").textContent = summary?.nearby_search === "sample_not_queried"
    ? "Nearby search was not called. The four Chicago places are sample suggestions."
    : summary?.nearby_search === "failed" ? "Nearby search failed. This plan contains only your resolved requested places; extra nearby activities were not invented."
    : summary?.search_center ? `Nearby search: within 3 km of ${summary.search_center.name}.` : "";
  $("trip-summary").textContent = `${result.request.trip.start_date} — ${result.request.trip.end_date} · ${result.request.trip.timezone}`;
  $("activity-count").textContent = result.request.trip.activities.length;
  $("fixed-count").textContent = result.request.original_fixed_events.length;
  $("source-count").textContent = result.sources.length;
  $("result-notes").replaceChildren(...result.notes.map((note) => element("p", note)));
  $("attribution").textContent = result.attributions.join(" · ");
  $("schedule").replaceChildren();
  const zone = result.request.trip.timezone;
  const formatDay = new Intl.DateTimeFormat("en-CA", { timeZone: zone, year: "numeric", month: "2-digit", day: "2-digit" });
  const formatTime = new Intl.DateTimeFormat("en-US", { timeZone: zone, hour: "2-digit", minute: "2-digit", hour12: false });
  let day = null;
  let previous = null;
  result.request.trip.activities.forEach((activity) => {
    const start = new Date(activity.start_time);
    const date = formatDay.format(start);
    if (day !== date) {
      $("schedule").append(element("h3", date, "day-title")); day = date; previous = null;
    }
    if (previous && previous.location.id !== activity.location.id) {
      const route = result.request.travel_times.find((t) => t.from_location_id === previous.location.id && t.to_location_id === activity.location.id);
      const text = route ? `${route.minutes} min ${result.data_mode === "demo" ? "example transfer" : "estimated driving"}` : "Travel time unverified";
      $("schedule").append(element("p", text, "transfer-note"));
    }
    const card = element("div", undefined, "activity");
    card.append(element("div", `${formatTime.format(start)} – ${formatTime.format(new Date(activity.end_time))}`, "activity-time"));
    const body = element("div");
    const name = element("div", activity.name, "activity-name");
    if (activity.fixed) name.append(element("span", "Fixed", "fixed-badge"));
    body.append(name, element("div", activity.location.name, "activity-place"));
    body.append(element("div", activity.estimated_cost === null ? "Cost unknown" : `Estimated $${Number(activity.estimated_cost).toFixed(2)}`, "activity-place"));
    const explanation = summary?.candidate_activities?.find((c) => c.location_id === activity.location.id);
    body.append(element("p", activity.fixed ? "Your fixed reservation: the supplied time and place are kept." : explanation?.reason || "Flexible visit fitted into an available time slot.", "activity-explanation"));
    card.append(body); $("schedule").append(card); previous = activity;
  });
  if (!result.request.trip.activities.length) $("schedule").append(element("p", "No activities could be scheduled."));
  result.research_steps.forEach(renderStep);
  renderSources(result.sources);
  renderPreparation(result.preparation);
  renderValidation(result.validation, result.data_mode);
}
