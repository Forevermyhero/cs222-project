/* Page controller: read the form, start/stop requests, and call the display functions.
   Network parsing lives in api.js; drawing results lives in render.js. */
import { requestJSON, streamPlan } from "./api.js";
import { $, element, renderResult, renderValidation, renderStep, resetResearch, stopResearch } from "./render.js";

let current = null;
let eventCounter = 0;
let controller = null;

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

function clearResult() {
  current = null;
  $("result-content").hidden = true;
  $("empty-state").hidden = false;
  $("preparation-panel").hidden = true;
}

function setBusy(busy) {
  $("trip-form").querySelectorAll("input,select,textarea,button").forEach((field) => { field.disabled = busy; });
  $("cancel-plan").disabled = false;
  $("cancel-plan").hidden = !busy;
}

async function loadExample() {
  try {
    const data = await requestJSON("/api/example");
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
    clearResult();
    $("empty-title").textContent = "The good part starts with a plan.";
    $("empty-copy").textContent = "Try the Chicago example. See a fixed interview stay put while four places find their way into the day.";
    $("research-panel").hidden = true;
    updateMode();
    showStatus("Example loaded. Build the itinerary when you're ready.");
  } catch (error) { showStatus(error.message, true); }
}

function updateMode() {
  $("mode-note").textContent = $("data-mode").value === "demo"
    ? "Example hours, prices and travel times are synthetic. No websites are contacted."
    : "Uses public map services without an API key. Watch each lookup in the research log; unavailable facts remain unverified.";
}

function formPayload() {
  const fixed = [...$("fixed-events").querySelectorAll("fieldset")].map((card) => ({
    id: card.dataset.id, name: card.querySelector('[name="event-name"]').value,
    location: card.querySelector('[name="event-location"]').value,
    start_time: card.querySelector('[name="event-start"]').value,
    end_time: card.querySelector('[name="event-end"]').value,
  }));
  return {
    destination: $("destination").value, start_date: $("start-date").value,
    end_date: $("end-date").value, timezone: $("timezone").value,
    preferences: $("preferences").value.split(",").map((s) => s.trim()).filter(Boolean),
    requested_places: $("requested-places").value.split("\n").map((s) => s.trim()).filter(Boolean),
    fixed_events: fixed, budget: $("budget").value || null,
    data_mode: $("data-mode").value, planner: "heuristic",
  };
}

$("trip-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const payload = formPayload();
  clearResult();
  resetResearch(payload.data_mode);
  $("empty-title").textContent = "Putting the pieces together.";
  $("empty-copy").textContent = "The research log shows the sources and checks behind this plan.";
  controller = new AbortController();
  setBusy(true);
  showStatus("Finding places, arranging activities and checking constraints…");
  try {
    current = await streamPlan(payload, renderStep, controller.signal);
    renderResult(current);
    $("preparation-panel").hidden = false;
    $("research-panel").open = false;
    showStatus("Your itinerary and constraint checks are ready.");
  } catch (error) {
    stopResearch();
    $("empty-title").textContent = "A little more information is needed.";
    $("empty-copy").textContent = "Your research log records what happened. Adjust the trip or try again when the source is available.";
    showStatus(error.name === "AbortError" ? "Stopped. No new itinerary was generated." : error.message, error.name !== "AbortError");
  } finally { setBusy(false); controller = null; }
});

$("load-example").addEventListener("click", loadExample);
$("add-event").addEventListener("click", () => addEvent());
$("data-mode").addEventListener("change", updateMode);
$("cancel-plan").addEventListener("click", () => controller?.abort());
$("revalidate").addEventListener("click", async () => {
  if (!current) return;
  try {
    const result = await requestJSON("/validate", current.request);
    current.validation = result;
    current.fully_checked = result.warnings.length === 0;
    renderValidation(result, current.data_mode);
    showStatus("Itinerary checked again.");
  } catch (error) { showStatus(error.message, true); }
});
$("download").addEventListener("click", () => {
  if (!current) return;
  const url = URL.createObjectURL(new Blob([JSON.stringify(current, null, 2)], { type: "application/json" }));
  const anchor = element("a"); anchor.href = url; anchor.download = "itinerary.json"; anchor.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
});
loadExample();
