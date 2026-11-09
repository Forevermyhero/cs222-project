/* Map-tool workbench. No model, scheduling, booking or arbitrary webpage fetching.
   HTTP mode uses our typed backend tools. A downloaded file can query three public
   CORS APIs directly from the user's browser; Nominatim stays backend-only so a
   file:// page never sends anonymous requests without an application referrer. */
"use strict";
const $ = (id) => document.getElementById(id);
const portable = location.protocol === "file:" || document.querySelector('meta[name="travel-tools-transport"]')?.content === "browser";
const labels = { city: "城市坐标 / Open-Meteo", place: "指定地点 / Nominatim", attractions: "附近景点 / Overpass", routes: "驾车时间 / OSRM" };
const state = { city: null, places: [], routes: null, records: [], mode: "live", controller: null };
const cache = new Map();
const demoRows = [
  ["art", "Art Institute of Chicago", 41.8796, -87.6237, "Mo-Su 10:00-17:00", "https://www.artic.edu/visit"],
  ["park", "Millennium Park", 41.8826, -87.6226, "Mo-Su 08:00-20:00", null],
  ["river", "Chicago Riverwalk", 41.8882, -87.6262, "Mo-Su 08:00-20:00", null],
  ["museum", "Field Museum", 41.8663, -87.6170, "Mo-Su 09:00-17:00", "https://www.fieldmuseum.org/visit"],
];
function node(tag, text, className) {
  const item = document.createElement(tag);
  if (text !== undefined) item.textContent = text;
  if (className) item.className = className;
  return item;
}
function safeAnchor(url, text) {
  try {
    const parsed = new URL(url);
    if (!["http:", "https:"].includes(parsed.protocol) || parsed.username || parsed.password) return null;
    const a = node("a", text); a.href = parsed.href; a.target = "_blank"; a.rel = "noopener noreferrer";
    return a;
  } catch { return null; }
}
function facts(values) {
  const list = node("dl");
  for (const [key, value] of Object.entries(values)) list.append(node("dt", key), node("dd", value ?? "未知 / 数据未提供"));
  return list;
}
function placeRecord(location, hours, website, sourceUrl = null) {
  return { location, opening_hours_raw: hours ?? null, website: website ?? null, source_url: sourceUrl,
    website_checked: false, cross_checked: false, ticket_price: null, hotel_availability: null };
}
function demoPlaces() {
  return demoRows.map(([id, name, latitude, longitude, hours, website]) =>
    placeRecord({ id: `demo:${id}`, name, latitude, longitude }, hours, website));
}
function showRecord(record) {
  const row = record.row;
  row.className = `log ${record.status}`;
  const top = node("div", undefined, "log-top");
  const status = { running: "正在查询", completed: "已收到数据", cached: "使用缓存", failed: "失败", example: "合成示例", stopped: "已停止等待" };
  top.append(node("strong", labels[record.tool]), node("span", status[record.status]));
  row.replaceChildren(top, node("p", record.detail));
  for (const url of record.source_urls || []) {
    const a = safeAnchor(url, url); if (a) row.append(a);
  }
  if (record.data !== null && record.data !== undefined) {
    const detail = node("details");
    detail.append(node("summary", "查看结构化返回数据"), node("pre", JSON.stringify(record.data, null, 2)));
    row.append(detail);
  }
  $("log-count").textContent = `${state.records.length} 次调用`;
}
async function readJSON(url, options = {}) {
  const control = new AbortController();
  const outer = state.controller.signal;
  const cancel = () => control.abort();
  outer.addEventListener("abort", cancel, { once: true });
  if (outer.aborted) control.abort();
  const timeout = setTimeout(cancel, 25000);
  try {
    const response = await fetch(url, { ...options, signal: control.signal, credentials: "omit" });
    const text = await response.text();
    if (text.length > 3000000) throw new Error("响应过大，已拒绝处理。");
    let data;
    try { data = JSON.parse(text); } catch { throw new Error(`HTTP ${response.status}：服务没有返回有效 JSON。`); }
    if (!response.ok) {
      const error = new Error(data.error || `HTTP ${response.status}`);
      error.research_steps = data.research_steps;
      if (data.detail) error.message += ` ${JSON.stringify(data.detail)}`;
      throw error;
    }
    return data;
  } finally { clearTimeout(timeout); outer.removeEventListener("abort", cancel); }
}
async function publicJSON(record, url) {
  record.source_urls = [url]; showRecord(record);
  const entry = cache.get(url);
  if (entry && Date.now() - entry.time < 900000) {
    record.status = "cached";
    return entry.data;
  }
  const data = await readJSON(url);
  if (cache.size >= 100) cache.delete(cache.keys().next().value);
  cache.set(url, { time: Date.now(), data });
  return data;
}
function coordinates(point) {
  return Number.isFinite(point.latitude) && Math.abs(point.latitude) <= 90 &&
    Number.isFinite(point.longitude) && Math.abs(point.longitude) <= 180;
}
async function directTool(tool, input, record) {
  if (tool === "city") {
    const query = new URLSearchParams({ name: input.destination, count: "1", language: "en", format: "json" });
    const data = await publicJSON(record, `https://geocoding-api.open-meteo.com/v1/search?${query}`);
    const city = data.results?.[0];
    if (!city) throw new Error("没有找到该城市。试试明确的英文城市名称。");
    const point = { id: `city:${city.id}`, name: city.name, latitude: city.latitude, longitude: city.longitude };
    if (!coordinates(point) || !city.timezone) throw new Error("城市数据缺少有效坐标或时区。");
    new Intl.DateTimeFormat("en", { timeZone: city.timezone });
    return { location: point, timezone: city.timezone };
  }
  if (tool === "attractions") {
    if (!coordinates(input.center)) throw new Error("城市坐标无效。");
    const { latitude, longitude } = input.center;
    const query = `[out:json][timeout:15];nwr(around:3000,${latitude},${longitude})["tourism"~"^(museum|attraction|gallery)$"];out center 16;`;
    const data = await publicJSON(record, `https://overpass-api.de/api/interpreter?${new URLSearchParams({ data: query })}`);
    if (!Array.isArray(data.elements)) throw new Error("Overpass 返回的数据结构无效。");
    return data.elements.flatMap((item) => {
      const tags = item.tags || {}, point = item.lat === undefined ? item.center : item;
      const loc = { id: `osm:${item.type}:${item.id}`, name: tags.name, latitude: point?.lat, longitude: point?.lon };
      if (!loc.name || !coordinates(loc) || !["node", "way", "relation"].includes(item.type) || !Number.isSafeInteger(item.id)) return [];
      return [placeRecord(loc, tags.opening_hours, tags.website || tags["contact:website"], `https://www.openstreetmap.org/${item.type}/${item.id}`)];
    }).sort((a, b) => a.location.name.localeCompare(b.location.name, "en")).slice(0, 6);
  }
  if (tool === "routes") {
    if (input.locations.some((p) => !coordinates(p))) throw new Error("路线地点缺少坐标。");
    const coords = input.locations.map((p) => `${p.longitude},${p.latitude}`).join(";");
    const data = await publicJSON(record, `https://router.project-osrm.org/table/v1/driving/${coords}?annotations=duration`);
    if (data.code !== "Ok" || !Array.isArray(data.durations) || data.durations.length !== input.locations.length) throw new Error("OSRM 没有返回有效时间矩阵。");
    const times = [];
    data.durations.forEach((row, i) => {
      if (!Array.isArray(row) || row.length !== input.locations.length) throw new Error("OSRM 矩阵行无效。");
      row.forEach((seconds, j) => {
        if (i === j || seconds === null) return;
        if (typeof seconds !== "number" || !Number.isFinite(seconds) || seconds < 0) throw new Error("OSRM 时间值无效。");
        times.push({ from_location_id: input.locations[i].id, to_location_id: input.locations[j].id, minutes: Math.ceil(seconds / 60) });
      });
    });
    return { mode: "driving", live_traffic: false, travel_times: times, distance_meters: null };
  }
  throw new Error("下载版不调用 Nominatim。请在后端网页使用明确地址查询。");
}
async function callTool(tool, input) {
  const record = { tool, input, status: "running", detail: "正在请求数据，尚未确认结果。", data: null,
    data_mode: state.mode, requested_at: new Date().toISOString(), source_urls: [], row: node("li") };
  state.records.push(record); $("logs").append(record.row); $("empty-log").hidden = true; showRecord(record);
  try {
    let data;
    if (state.mode === "demo") {
      if (tool === "city") data = { location: { id: "demo:city", name: "Chicago", latitude: 41.881, longitude: -87.629 }, timezone: "America/Chicago" };
      if (tool === "attractions") data = demoPlaces();
      if (tool === "place") {
        data = demoPlaces().find((p) => p.location.name.toLowerCase().includes(input.name.toLowerCase()));
        if (!data) throw new Error("离线示例不包含该地点；不会伪造地点数据。");
      }
      if (tool === "routes") data = { mode: "driving", live_traffic: false, distance_meters: null, travel_times:
        input.locations.flatMap((a) => input.locations.filter((b) => a.id !== b.id).map((b) => ({ from_location_id: a.id, to_location_id: b.id, minutes: 20 }))) };
      record.status = "example";
      record.detail = "读取合成示例，没有访问任何外部服务。坐标、营业时间和交通估计不代表最新事实。";
    } else if (portable) {
      data = await directTool(tool, input, record);
      if (record.status !== "cached") record.status = "completed";
      record.detail = record.status === "cached" ? "使用本页 15 分钟内的缓存，本次未重新查询。" : "浏览器收到公开 API 的 JSON；未访问景点官网。";
    } else {
      const response = await readJSON(`/api/tools/${tool}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(input) });
      data = response.data;
      record.research_steps = response.research_steps;
      record.source_urls = [...new Set(response.research_steps.map((s) => s.url).filter(Boolean))];
      record.status = response.research_steps.some((s) => s.status === "cached") ? "cached" : "completed";
      record.detail = record.status === "cached" ? "后端使用了缓存，查看来源记录可核对。" : "后端返回已整理的公开地图数据；未访问景点官网。";
    }
    record.data = data; showRecord(record); $("export").disabled = false; return data;
  } catch (error) {
    record.status = state.controller.signal.aborted ? "stopped" : "failed";
    record.detail = error.name === "AbortError" ? "请求超时或已停止等待，结果未确认。" : error.message;
    if (portable && error instanceof TypeError) record.detail += " 请检查网络或该服务的跨域访问限制；未替换成示例数据。";
    record.research_steps = error.research_steps || [];
    if (record.research_steps.length) record.source_urls = record.research_steps.map((s) => s.url).filter(Boolean);
    showRecord(record); $("export").disabled = false; throw error;
  }
}
function renderCity() {
  $("city-panel").hidden = false; $("city-title").textContent = state.city.location.name;
  const p = state.city.location;
  $("city-facts").replaceChildren(facts({ 纬度: p.latitude, 经度: p.longitude, 当地时区: state.city.timezone,
    数据来源: state.mode === "demo" ? "合成示例，未联网" : "Open-Meteo / GeoNames；当前采用第一个匹配结果" }));
}
function renderPlaces() {
  $("places").replaceChildren();
  for (const p of state.places) {
    const card = node("article", undefined, "place-card");
    card.append(node("h3", p.location.name), facts({ 地点标识: p.location.id, 纬度: p.location.latitude, 经度: p.location.longitude,
      营业时间原文: p.opening_hours_raw, 核实状态: state.mode === "demo" ? "合成示例，未联网" : "仅地图来源，尚未与官网交叉核对", 门票价格: null }));
    const mapURL = p.source_url || `https://www.openstreetmap.org/?mlat=${p.location.latitude}&mlon=${p.location.longitude}#map=16/${p.location.latitude}/${p.location.longitude}`;
    const map = safeAnchor(mapURL, "在地图中查看坐标 / 记录"); if (map) card.append(map);
    const site = safeAnchor(p.website, "地图中的网站标签 · 尚未抓取核实");
    if (site) card.append(site); else card.append(node("p", "没有可用的网站标签", "hint"));
    $("places").append(card);
  }
  $("place-count").textContent = `${state.places.length} 个地点`;
  $("empty-places").hidden = state.places.length > 0;
  for (const id of ["from", "to"]) $(id).replaceChildren(...state.places.map((p) => { const o = node("option", p.location.name); o.value = p.location.id; return o; }));
  if (state.places.length > 1) $("to").selectedIndex = 1;
}
async function queryRoute() {
  state.routes = null;
  $("route-result").replaceChildren();
  const a = state.places.find((p) => p.location.id === $("from").value);
  const b = state.places.find((p) => p.location.id === $("to").value);
  if (!a || !b || a.location.id === b.location.id) throw new Error("请选择两个不同地点。");
  const data = await callTool("routes", { locations: [a.location, b.location] }); state.routes = data;
  for (const [source, target] of [[a, b], [b, a]]) {
    const t = data.travel_times.find((t) => t.from_location_id === source.location.id && t.to_location_id === target.location.id);
    const card = node("div", undefined, "route-card");
    card.append(node("span", `${source.location.name} → ${target.location.name}`), node("strong", t ? `${t.minutes} 分钟` : "路线时间未知"),
      node("small", state.mode === "demo" ? "合成的 20 分钟示例" : "OSRM 驾车估计 · 不含实时路况"));
    $("route-result").append(card);
  }
}
function updateMode() {
  $("place").disabled = portable && $("mode").value === "live";
  $("place-note").textContent = portable && $("mode").value === "live"
    ? "下载版从附近景点中选择地点。明确地址解析保留在后端，以满足 Nominatim 的应用标识和限流要求。"
    : "Nominatim 解析一个明确地点；不做自动补全。离线示例仅支持四个示例景点。";
}
function busy(value) {
  for (const id of ["city", "mode", "place", "run", "from", "to", "route"]) $(id).disabled = value;
  $("stop").hidden = !value;
  if (!value) {
    updateMode();
    for (const id of ["from", "to", "route"]) $(id).disabled = state.places.length < 2;
  }
}
$("tools-form").addEventListener("submit", async (event) => {
  event.preventDefault(); state.controller = new AbortController(); state.mode = $("mode").value;
  state.city = null; state.places = []; state.routes = null; state.records = [];
  $("logs").replaceChildren(); $("route-result").replaceChildren(); $("city-panel").hidden = true;
  $("log-count").textContent = "0 次调用"; $("export").disabled = true; renderPlaces();
  const destination = $("city").value.trim(), name = $("place").disabled ? "" : $("place").value.trim();
  busy(true); $("status").textContent = "正在定位城市，然后查询附近景点…";
  try {
    if (state.mode === "demo" && destination.toLowerCase() !== "chicago") throw new Error("离线示例仅包含 Chicago。其他城市请选择真实公开数据。");
    state.city = await callTool("city", { destination }); renderCity();
    if (name) { state.places.push(await callTool("place", { destination, name })); renderPlaces(); }
    const nearby = await callTool("attractions", { center: state.city.location });
    state.places = [...new Map([...state.places, ...nearby].map((p) => [p.location.id, p])).values()].slice(0, 8); renderPlaces();
    if (state.places.length >= 2) {
      $("status").textContent = "地点数据已返回，正在查询前两个地点的驾车时间…";
      await queryRoute();
    }
    $("status").textContent = state.places.length ? "查询完成。可切换 A/B 再查交通，或展开每次调用的结构化数据。" : "城市定位成功，但附近未找到可用景点；未补造地点。";
  } catch (error) { $("status").textContent = `查询未完成：${error.message} 已取得的数据和失败记录会保留。`; }
  finally { busy(false); state.controller = null; }
});
$("route").addEventListener("click", async () => {
  state.controller = new AbortController(); busy(true);
  try { await queryRoute(); $("status").textContent = "路线查询完成；两个方向分别显示。"; }
  catch (error) { $("status").textContent = error.message; }
  finally { busy(false); state.controller = null; }
});
$("mode").addEventListener("change", updateMode);
$("stop").addEventListener("click", () => state.controller?.abort());
$("export").addEventListener("click", () => {
  const data = { data_mode: state.mode, transport: portable ? "portable_browser" : "backend", city: state.city, places: state.places, routes: state.routes,
    records: state.records.map(({ row, ...record }) => record), llm_connected: false, cross_checked: false };
  const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: "application/json" }));
  const a = node("a"); a.href = url; a.download = "travel-tool-evidence.json"; a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
});
$("transport-note").textContent = portable
  ? "下载独立版：无需启动服务器。真实模式由你的浏览器查询 Open-Meteo、Overpass 和 OSRM；网络或跨域失败会明确显示。Nominatim 明确地址查询需要后端版。离线示例随时可用。"
  : "后端版：使用四个带输入校验的独立工具接口。公开服务失败会显示原因，不会自动替换为示例。也可下载独立版，在自己的浏览器中使用三个公开数据工具。";
updateMode();
