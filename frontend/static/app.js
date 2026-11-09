"use strict";

const $ = (id) => document.getElementById(id);
let current = null;
let eventCounter = 0;

async function api(path, payload) {
  const response = await fetch(path, payload === undefined ? {} : {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload),
  });
  const data = await response.json();
  if (!response.ok) {
    const fields = (data.detail || []).map((item) => `${item.loc.join(".")}: ${item.msg}`).join("; ");
    throw new Error(fields || data.error || "The request could not be completed.");
  }
  return data;
}

function element(tag, text, className) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (className) node.className = className;
  return node;
}

function addEvent(data = {}) {
  const fragment = $("event-template").content.cloneNode(true);
  const card = fragment.querySelector("fieldset");
  card.dataset.id = data.id || `event-${++eventCounter}`;
  for (const [name, value] of Object.entries({
    "event-name": data.name, "event-location": data.location,
    "event-start": data.start_time, "event-end": data.end_time,
  })) card.querySelector(`[name="${name}"]`).value = value || "";
  card.querySelector(".remove-event").addEventListener("click", () => card.remove());
  $("fixed-events").append(fragment);
}

function showStatus(message, error = false) {
  $("form-status").textContent = message;
  $("form-status").classList.toggle("error", error);
}

async function loadExample() {
  try {
    const data = await api("/api/example");
    $("destination").value = data.destination;
    $("start-date").value = data.start_date;
    $("end-date").value = data.end_date;
    $("timezone").value = data.timezone;
    $("preferences").value = data.preferences.join(", ");
    $("requested-places").value = data.requested_places.join("\n");
    $("budget").value = data.budget;
    $("data-mode").value = data.data_mode;
    $("planner").value = data.planner;
    $("fixed-events").replaceChildren();
    data.fixed_events.forEach(addEvent);
    updateMode();
    showStatus("Example loaded. Build the itinerary when you're ready.");
  } catch (error) { showStatus(error.message, true); }
}

function updateMode() {
  $("mode-note").textContent = $("data-mode").value === "demo"
    ? "Example opening hours, prices and travel times are synthetic. They do not describe current conditions."
    : "Uses public map services. Driving estimates exclude live traffic. Missing or unsupported opening data will remain unverified.";
}

function renderValidation(validation, mode) {
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

function render(result) {
  current = result;
  $("empty-state").hidden = true;
  $("result-content").hidden = false;
  $("result-mode").textContent = `${result.data_mode === "demo" ? "Example" : "Public map"} data / ${result.planner === "heuristic" ? "rule-based plan" : "OpenAI candidate"}`;
  $("result-notes").replaceChildren(...result.notes.map((note) => element("p", note)));
  $("attribution").textContent = result.attributions.join(" · ");
  $("schedule").replaceChildren();
  const zone = result.request.trip.timezone;
  const formatDay = new Intl.DateTimeFormat("en-CA", { timeZone: zone, year: "numeric", month: "2-digit", day: "2-digit" });
  const formatTime = new Intl.DateTimeFormat("en-US", { timeZone: zone, hour: "2-digit", minute: "2-digit", hour12: false });
  let day = null;
  result.request.trip.activities.forEach((activity) => {
    const start = new Date(activity.start_time);
    const date = formatDay.format(start);
    if (day !== date) { $("schedule").append(element("h3", date, "day-title")); day = date; }
    const card = element("div", undefined, "activity");
    card.append(element("div", `${formatTime.format(start)} – ${formatTime.format(new Date(activity.end_time))}`, "activity-time"));
    const body = element("div");
    const name = element("div", activity.name, "activity-name");
    if (activity.fixed) name.append(element("span", "Fixed", "fixed-badge"));
    body.append(name, element("div", activity.location.name, "activity-place"));
    body.append(element("div", activity.estimated_cost === null ? "Cost unknown" : `Estimated $${Number(activity.estimated_cost).toFixed(2)}`, "activity-place"));
    card.append(body);
    $("schedule").append(card);
  });
  if (!result.request.trip.activities.length) $("schedule").append(element("p", "No activities could be scheduled."));
  renderValidation(result.validation, result.data_mode);
}

$("trip-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const fixed = [...$("fixed-events").querySelectorAll("fieldset")].map((card) => ({
    id: card.dataset.id, name: card.querySelector('[name="event-name"]').value,
    location: card.querySelector('[name="event-location"]').value,
    start_time: card.querySelector('[name="event-start"]').value,
    end_time: card.querySelector('[name="event-end"]').value,
  }));
  const payload = {
    destination: $("destination").value, start_date: $("start-date").value,
    end_date: $("end-date").value, timezone: $("timezone").value,
    preferences: $("preferences").value.split(",").map((s) => s.trim()).filter(Boolean),
    requested_places: $("requested-places").value.split("\n").map((s) => s.trim()).filter(Boolean),
    fixed_events: fixed, budget: $("budget").value || null,
    data_mode: $("data-mode").value, planner: $("planner").value,
  };
  $("plan-button").disabled = true;
  showStatus("Finding places, arranging activities and checking constraints…");
  try { render(await api("/api/plan", payload)); showStatus("Your itinerary and constraint checks are ready."); }
  catch (error) { showStatus(error.message, true); }
  finally { $("plan-button").disabled = false; }
});

$("load-example").addEventListener("click", loadExample);
$("add-event").addEventListener("click", () => addEvent());
$("data-mode").addEventListener("change", updateMode);
$("revalidate").addEventListener("click", async () => {
  if (!current) return;
  try {
    const result = await api("/validate", current.request);
    current.validation = result;
    renderValidation(result, current.data_mode);
    showStatus("Itinerary checked again.");
  } catch (error) { showStatus(error.message, true); }
});
$("download").addEventListener("click", () => {
  if (!current) return;
  const url = URL.createObjectURL(new Blob([JSON.stringify(current, null, 2)], { type: "application/json" }));
  const anchor = element("a"); anchor.href = url; anchor.download = "itinerary.json"; anchor.click();
  URL.revokeObjectURL(url);
});
api("/api/health").then((health) => { $("openai-option").disabled = !health.openai_configured; })
  .catch((error) => showStatus(error.message, true));
loadExample();
