/* Transport only: JSON calls and real progress events from the Flask backend. */
async function failure(response) {
  const data = await response.json();
  const fields = (data.detail || []).map((item) => `${item.loc.join(".")}: ${item.msg}`).join("; ");
  throw new Error(fields || data.error || "The request could not be completed.");
}

export async function requestJSON(path, payload) {
  const response = await fetch(path, payload === undefined ? {} : {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload),
  });
  if (!response.ok) return failure(response);
  return response.json();
}

export async function streamPlan(payload, onStep, signal) {
  const response = await fetch("/api/plan/stream", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload), signal,
  });
  if (!response.ok) return failure(response);
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let result = null;
  function receive(line) {
    if (!line.trim()) return;
    const event = JSON.parse(line);
    if (event.type === "progress") onStep(event.step);
    if (event.type === "error") throw new Error(event.error);
    if (event.type === "result") result = event.result;
  }
  try {
    while (true) {
      const { done, value } = await reader.read();
      buffer += decoder.decode(value, { stream: !done });
      let end;
      while ((end = buffer.indexOf("\n")) !== -1) {
        receive(buffer.slice(0, end));
        buffer = buffer.slice(end + 1);
      }
      if (done) break;
    }
    receive(buffer);
  } finally { reader.releaseLock(); }
  if (!result) throw new Error("The connection ended before a complete itinerary arrived.");
  return result;
}
