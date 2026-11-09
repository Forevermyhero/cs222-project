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

export function resetResearch(mode) {
  rows.clear(); records.clear();
  $("research-steps").replaceChildren();
  $("source-cards").replaceChildren();
  $("research-panel").hidden = false;
  $("research-panel").open = true;
  $("research-mode").textContent = mode === "demo" ? "Example walkthrough" : "Live source requests";
  $("research-disclaimer").textContent = mode === "demo"
    ? "Offline example. No live websites are visited, and no LLM is connected."
    : "These are the backend's actual requests. Cached results and failed lookups are labeled.";
  $("research-count").textContent = "Starting";
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
  const status = { completed: "Done", cached: "Cached", running: "In progress", example: "Example", failed: "Failed", stopped: "Stopped" };
  top.append(element("strong", step.title), element("span", status[step.status] || step.status, "step-status"));
  body.append(top, element("p", step.detail));
  const source = link(step.url, `${step.provider} · view source response`);
  if (source) body.append(source);
  row.replaceChildren(element("span", undefined, "step-dot"), body);
  $("research-count").textContent = `${rows.size} steps`;
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
    const label = source.data_mode === "demo" ? "Example hours" : source.hours_status === "usable" ? "Reported hours" : "Hours unverified";
    card.append(element("p", label, "eyebrow"), element("h4", source.name),
      element("p", source.opening_hours || "No usable opening-hour data was supplied."));
    const map = link(source.source_url, "View map record");
    const venue = link(source.website_url, "Venue website · not checked here");
    if (map) card.append(map);
    if (venue) card.append(venue);
    if (source.data_mode === "demo") card.append(element("small", "Reference links were not fetched in this run."));
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
  $("result-mode").textContent = `${result.data_mode === "demo" ? "Example" : "Public map"} data / rule-based plan`;
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
    card.append(body); $("schedule").append(card); previous = activity;
  });
  if (!result.request.trip.activities.length) $("schedule").append(element("p", "No activities could be scheduled."));
  result.research_steps.forEach(renderStep);
  renderSources(result.sources);
  renderPreparation(result.preparation);
  renderValidation(result.validation, result.data_mode);
}
