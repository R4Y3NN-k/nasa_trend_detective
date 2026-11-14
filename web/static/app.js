// SI-assisted: parts of this file were drafted with Claude (Anthropic) and reviewed by the team
// Trend Detective map-first UI. Owner: C (dashboard). Talks to web/server.py.
'use strict';

// ---------------------------------------------------------------- MERRA-2 grid (same snapping as td/fetch.py)
const DLAT = 0.5, DLON = 0.625;
const snap = (lat, lon) => [
  +(Math.floor(lat / DLAT + 0.5) * DLAT).toFixed(4),
  +(-180 + Math.floor((lon + 180) / DLON + 0.5) * DLON).toFixed(4),
];
const keyOf = (lat, lon) => `${lat.toFixed(4)},${lon.toFixed(4)}`;

function cellsIn(south, west, north, east, stride) {
  const out = [];
  const i0 = Math.ceil(south / DLAT), i1 = Math.floor(north / DLAT);
  const j0 = Math.ceil((west + 180) / DLON), j1 = Math.floor((east + 180) / DLON);
  for (let i = i0; i <= i1; i++) {
    if (i % stride) continue;
    for (let j = j0; j <= j1; j++) {
      if (j % stride) continue;
      out.push([+(i * DLAT).toFixed(4), +(-180 + j * DLON).toFixed(4)]);
    }
  }
  return out;
}

function insidePolygon(lat, lon, poly) {
  let hit = false;
  for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
    const yi = poly[i].lat, xi = poly[i].lng, yj = poly[j].lat, xj = poly[j].lng;
    if ((yi > lat) !== (yj > lat) && lon < (xj - xi) * (lat - yi) / (yj - yi) + xi) hit = !hit;
  }
  return hit;
}

// ---------------------------------------------------------------- state
const S = {
  meta: null,
  mode: 'draw',               // 'draw' | 'points'
  picked: new Map(),          // key -> [lat, lon]
  questions: [], regionType: null,
  question: null, variable: null,
  years: [1981, 2025],
  screen: 'pick',             // 'pick' | 'loading' | 'verdict'
  result: null, error: null,
  cross: null,                // second-dataset check: {status: 'loading'|'ok'|'error', data|error}
  tab: 'series', view: 'anomaly',
  capped: false,
  pd: new Map(),              // key -> NASA POWER data for that cell: {status: 'queued'|'loading'|'ok'|'error', ...}
};

// Colour ramps for the real per-point means (light = low, dark = high).
const RAMPS = {
  T2M: [[253, 231, 212], [194, 65, 12]],
  PRECTOTCORR: [[220, 232, 251], [29, 78, 216]],
  GWETTOP: [[237, 227, 209], [4, 100, 96]],
};

const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const $ = (id) => document.getElementById(id);

async function api(path, body) {
  const resp = await fetch(path, body === undefined ? {} : {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
  });
  const data = await resp.json().catch(() => ({ error: 'The server sent an unreadable answer.' }));
  if (!resp.ok) throw new Error(data.error || `Server error ${resp.status}`);
  return data;
}

// ---------------------------------------------------------------- map
const map = L.map('map', { zoomControl: false, attributionControl: true, minZoom: 3 }).setView([34.2, 9.6], 6);
L.control.zoom({ position: 'topleft' }).addTo(map);
L.tileLayer('https://{s}.tile.openstreetmap.fr/hot/{z}/{x}/{y}.png', {
  maxZoom: 18, subdomains: 'abc',
  attribution: '© OpenStreetMap contributors, tiles HOT · data NASA POWER (MERRA-2)',
}).addTo(map);

const pointsLayer = L.layerGroup().addTo(map);
const zonesLayer = L.layerGroup().addTo(map);
let lasso = null;

function setMode(mode) {
  S.mode = mode;
  const drawing = mode === 'draw';
  map.getContainer().classList.toggle('drawing', drawing);
  if (drawing) { map.dragging.disable(); map.boxZoom.disable(); } else { map.dragging.enable(); map.boxZoom.enable(); }
  for (const [id, on] of [['tool-draw', drawing], ['tool-points', !drawing]]) {
    const b = $(id);
    b.setAttribute('aria-pressed', String(on));
    b.className = 'w-11 h-11 flex items-center justify-center border-b border-line ' + (on ? 'bg-charcoal text-white' : 'bg-white text-ink hover:bg-land');
  }
  updateHint();
  renderPoints();
}

function updateHint() {
  const n = S.picked.size;
  if (S.screen === 'verdict') $('hint-text').textContent = `Verdict for the ${n} point${n === 1 ? '' : 's'} shown · Back to change the area`;
  else if (S.screen === 'loading') $('hint-text').textContent = 'Fetching NASA POWER data…';
  else if (S.mode === 'draw') $('hint-text').textContent = 'Draw around the area you want to investigate, or switch to points and tap them';
  else $('hint-text').textContent = `Tap grid points to add or remove them (up to ${S.meta ? S.meta.max_points : 30})`;
}

function renderPoints() {
  pointsLayer.clearLayers();
  const cap = S.meta ? S.meta.max_points : 30;
  const show = new Map(S.picked);
  if (S.mode === 'points' && S.screen === 'pick') {
    const b = map.getBounds();
    let stride = 1, cells;
    do { cells = cellsIn(b.getSouth(), b.getWest(), b.getNorth(), b.getEast(), stride); stride++; } while (cells.length > 700);
    for (const [lat, lon] of cells) if (!show.has(keyOf(lat, lon))) show.set(keyOf(lat, lon), [lat, lon]);
  }
  const ramp = rampFor();
  for (const [key, [lat, lon]] of show) {
    const on = S.picked.has(key);
    const d = S.pd.get(key);
    let style;
    if (!on) {
      style = { radius: 4, color: '#1B2A8C', weight: 1.5, fillColor: '#FFFFFF', fillOpacity: 1 };
    } else if (d && d.status === 'ok' && !d.land) {
      style = { radius: 6, color: '#5A5B60', weight: 2, fillColor: '#FFFFFF', fillOpacity: 1, dashArray: '2 3' };
    } else if (d && d.status === 'ok') {
      style = { radius: 8, color: '#FFFFFF', weight: 2, fillColor: ramp.color(d.means[ramp.var]), fillOpacity: 1 };
    } else if (d && d.status === 'error') {
      style = { radius: 6, color: '#B42318', weight: 2.5, fillColor: '#FFFFFF', fillOpacity: 1 };
    } else {
      style = { radius: 6, color: '#046460', weight: 2, fillColor: '#FFFFFF', fillOpacity: 1, dashArray: d && d.status === 'loading' ? '3 3' : null };
    }
    // Clickable for toggling in points mode; hoverable everywhere so people can read the real values.
    const m = L.circleMarker([lat, lon], { ...style, interactive: on || (S.mode === 'points' && S.screen === 'pick') });
    m.bindTooltip(on ? pointTooltip(lat, lon, d) : `${lat.toFixed(2)}°, ${lon.toFixed(2)}° · tap to add`, { direction: 'top' });
    m.on('click', () => {
      if (S.mode !== 'points' || S.screen !== 'pick') return;
      if (S.picked.has(key)) S.picked.delete(key);
      else if (S.picked.size >= cap) { flash(`At most ${cap} points: NASA POWER is asked once per point.`); return; }
      else S.picked.set(key, [lat, lon]);
      if (lasso) { lasso.remove(); lasso = null; }
      selectionChanged();
    });
    m.addTo(pointsLayer);
  }
}

// Freehand lasso on the map container.
(function setupLasso() {
  const el = map.getContainer();
  let drawing = false, path = [], line = null;
  el.addEventListener('pointerdown', (e) => {
    if (S.mode !== 'draw' || S.screen !== 'pick' || e.button !== 0) return;
    if (e.target.closest('.leaflet-control')) return;
    drawing = true;
    path = [map.mouseEventToLatLng(e)];
    if (lasso) { lasso.remove(); lasso = null; }
    line = L.polyline(path, { color: '#046460', weight: 3, dashArray: '8 6', interactive: false }).addTo(map);
    try { el.setPointerCapture(e.pointerId); } catch (_) { /* pen/synthetic pointers: drawing still works */ }
    e.preventDefault();
  });
  el.addEventListener('pointermove', (e) => {
    if (!drawing) return;
    const ll = map.mouseEventToLatLng(e);
    const last = map.latLngToContainerPoint(path[path.length - 1]);
    if (last.distanceTo(map.latLngToContainerPoint(ll)) < 4) return;
    path.push(ll);
    line.setLatLngs(path);
  });
  const finish = () => {
    if (!drawing) return;
    drawing = false;
    line.remove();
    if (path.length < 5) return;
    lasso = L.polygon(path, { color: '#046460', weight: 3, dashArray: '10 6', fillColor: '#046460', fillOpacity: 0.12, interactive: false }).addTo(map);
    selectInside(path);
  };
  el.addEventListener('pointerup', finish);
  el.addEventListener('pointercancel', finish);
})();

function selectInside(poly) {
  const lats = poly.map((p) => p.lat), lons = poly.map((p) => p.lng);
  const cap = S.meta ? S.meta.max_points : 30;
  let stride = 1, inside;
  do {
    inside = cellsIn(Math.min(...lats), Math.min(...lons), Math.max(...lats), Math.max(...lons), stride)
      .filter(([lat, lon]) => insidePolygon(lat, lon, poly));
    stride++;
  } while (inside.length > cap);
  if (!inside.length) {
    const c = L.polygon(poly).getBounds().getCenter();
    inside = [snap(c.lat, c.lng)];
  }
  S.capped = stride > 2;
  S.picked = new Map(inside.map(([lat, lon]) => [keyOf(lat, lon), [lat, lon]]));
  selectionChanged();
}

// ---------------------------------------------------------------- real NASA POWER data per picked point
const PD_WORKERS = 4;  // same politeness as td/fetch.py
let pdQueue = [], pdActive = 0, pdFrame = 0;

function queuePointData() {
  for (const [key, ll] of S.picked) {
    const d = S.pd.get(key);
    if (!d || d.status === 'error') { S.pd.set(key, { status: 'queued' }); pdQueue.push([key, ll]); }
  }
  pumpPointData();
}

function pumpPointData() {
  while (pdActive < PD_WORKERS && pdQueue.length) {
    const [key, [lat, lon]] = pdQueue.shift();
    if (!S.picked.has(key)) { S.pd.delete(key); continue; }   // deselected before its turn
    pdActive++;
    S.pd.set(key, { status: 'loading' });
    api('/api/point', { lat, lon })
      .then((d) => S.pd.set(key, { status: 'ok', ...d }))
      .catch((err) => S.pd.set(key, { status: 'error', error: err.message }))
      .finally(() => { pdActive--; pdChanged(); pumpPointData(); });
  }
  pdChanged();
}

function pdChanged() {
  if (pdFrame) return;
  pdFrame = requestAnimationFrame(() => { pdFrame = 0; renderPoints(); renderPdStatus(); });
}

function pdCounts() {
  const c = { total: S.picked.size, ok: 0, land: 0, sea: 0, error: 0, pending: 0 };
  for (const key of S.picked.keys()) {
    const d = S.pd.get(key);
    if (!d || d.status === 'queued' || d.status === 'loading') c.pending++;
    else if (d.status === 'error') c.error++;
    else { c.ok++; if (d.land) c.land++; else c.sea++; }
  }
  return c;
}

function rampFor() {
  const vid = chosenVars().primary || 'T2M';
  const [lo, hi] = RAMPS[vid] || RAMPS.T2M;
  const vals = [...S.picked.keys()].map((k) => S.pd.get(k)).filter((d) => d && d.status === 'ok' && d.land)
    .map((d) => d.means[vid]).filter((v) => v !== null && v !== undefined);
  const min = vals.length ? Math.min(...vals) : 0, max = vals.length ? Math.max(...vals) : 1;
  return {
    var: vid, min, max, n: vals.length, lo, hi,
    color: (v) => (v === null || v === undefined ? '#9A9B9F' : mix(lo, hi, max > min ? (v - min) / (max - min) : 0.6)),
  };
}

function valueText(vid, v) {
  const info = S.meta.variables[vid] || { name: vid, units: '', decimals: 2 };
  return v === null || v === undefined ? '–' : `${Number(v).toFixed(info.decimals ?? 2)} ${info.units || ''}`.trim();
}

function pointTooltip(lat, lon, d) {
  const head = `<strong>NASA POWER cell ${lat.toFixed(2)}°, ${lon.toFixed(2)}°</strong>`;
  if (!d || d.status === 'queued') return `${head}<br>Waiting to load…`;
  if (d.status === 'loading') return `${head}<br>Loading from NASA POWER…`;
  if (d.status === 'error') return `${head}<br>Could not load: ${esc(d.error)}`;
  if (!d.land) return `${head}<br>Sea (topsoil wetness saturated): skipped in the average`;
  const rows = Object.keys(S.meta.variables).filter((v) => v in d.means)
    .map((v) => `${esc(S.meta.variables[v].name)}: <strong>${esc(valueText(v, d.means[v]))}</strong>`).join('<br>');
  return `${head} · land<br>${rows}<br><span style="color:#5A5B60">Mean ${d.first} to ${d.last} · ${d.months} months</span>`;
}

function renderPdStatus() {
  const box = $('pd-status');
  if (!box) return;
  const c = pdCounts();
  if (!c.total) { box.innerHTML = ''; return; }
  const done = c.ok + c.error;
  const ramp = rampFor();
  const info = S.meta.variables[ramp.var] || { name: ramp.var };
  const loading = c.pending > 0;
  box.innerHTML = `
    <div class="flex flex-col gap-2 px-3.5 py-3 border border-line rounded-lg">
      <div class="flex items-center justify-between text-[13px]">
        <span class="font-bold">NASA data in your area</span>
        <span class="text-muted">${loading ? `${done} / ${c.total} loaded` : 'NASA POWER · MERRA-2'}</span>
      </div>
      ${loading ? `<div class="h-1.5 bg-land rounded-full overflow-hidden"><div class="h-full bg-teal transition-all" style="width:${Math.round(100 * done / c.total)}%"></div></div>` : ''}
      <div class="flex flex-wrap gap-x-3 gap-y-1 text-[13px] text-charcoal">
        <span class="flex items-center gap-1.5"><span class="inline-block w-2.5 h-2.5 rounded-full bg-teal"></span>${c.land} land</span>
        <span class="flex items-center gap-1.5"><span class="inline-block w-2.5 h-2.5 rounded-full border-2 border-dashed border-muted"></span>${c.sea} sea, skipped</span>
        ${c.error ? `<span class="flex items-center gap-1.5 text-[#B42318]"><span class="inline-block w-2.5 h-2.5 rounded-full border-2 border-[#B42318]"></span>${c.error} failed</span>` : ''}
      </div>
      ${ramp.n ? `<div class="flex flex-col gap-1">
        <div class="h-2.5 rounded-full" style="background:linear-gradient(90deg, rgb(${ramp.lo.join(',')}), rgb(${ramp.hi.join(',')}))"></div>
        <div class="flex justify-between text-[11px] text-muted"><span>${esc(valueText(ramp.var, ramp.min))}</span><span>${esc(info.name)}, mean ${S.meta.years[0]}–${S.meta.years[1]}</span><span>${esc(valueText(ramp.var, ramp.max))}</span></div>
      </div>` : ''}
      <span class="text-[12px] text-muted">Hover a point to see what NASA recorded there.</span>
    </div>`;
}

let areaTimer = null;
function selectionChanged() {
  queuePointData();
  renderPoints();
  renderPanel();
  clearTimeout(areaTimer);
  areaTimer = setTimeout(loadQuestions, 250);
}

async function loadQuestions() {
  try {
    const data = await api('/api/area', { points: [...S.picked.values()] });
    S.questions = data.questions;
    S.regionType = data.region_type;
    if (!S.variable && !S.questions.some((q) => q.id === S.question)) S.question = S.questions[0] ? S.questions[0].id : null;
  } catch (err) {
    S.error = err.message;
  }
  renderPanel();
}

let flashTimer = null;
function flash(text) {
  $('hint-text').textContent = text;
  clearTimeout(flashTimer);
  flashTimer = setTimeout(() => { flashTimer = null; updateHint(); }, 2600);
}

// ---------------------------------------------------------------- panel: pick screen
const H2 = 'text-[13px] font-bold tracking-wider uppercase text-teal';

function chosenVars() {
  if (S.variable) return { primary: S.variable, linked: null, why: '' };
  const q = S.questions.find((x) => x.id === S.question);
  return q ? { primary: q.primary, linked: q.linked, why: q.why } : { primary: null, linked: null, why: '' };
}

function yearOptions(selected, from, to) {
  let html = '';
  for (let y = from; y <= to; y++) html += `<option value="${y}" ${y === selected ? 'selected' : ''}>${y}</option>`;
  return html;
}

function renderPick() {
  const n = S.picked.size;
  const [y0, y1] = S.years;
  const [first, last] = S.meta.years;
  const typeLine = S.regionType ? `Ranked for a ${esc(S.regionType)} area` : 'Common questions about climate trends';
  const qCards = S.questions.map((q, i) => {
    const sel = !S.variable && S.question === q.id;
    return `<button type="button" data-q="${esc(q.id)}" aria-pressed="${sel}"
      class="w-full flex items-center gap-3.5 min-h-[64px] px-3.5 py-3 rounded-lg text-left ${sel ? 'border-2 border-teal bg-teal-soft' : 'border border-line bg-white m-px hover:border-[#B9B9B4]'}">
      <span class="flex-none w-8 h-8 rounded-full flex items-center justify-center text-sm font-bold ${sel ? 'bg-teal text-white' : 'bg-land text-charcoal'}">${i + 1}</span>
      <span class="flex-1 flex flex-col gap-0.5"><span class="text-base font-bold">${esc(q.label)}</span><span class="text-[13px] text-charcoal">${esc(q.vars)}</span></span>
      <span class="font-bold text-teal ${sel ? '' : 'invisible'}" aria-hidden="true">✓</span></button>`;
  }).join('');
  const chips = Object.entries(S.meta.variables).map(([id, v]) => {
    const sel = S.variable === id;
    return `<button type="button" data-v="${esc(id)}" aria-pressed="${sel}"
      class="min-h-[40px] px-3.5 py-2 rounded-full text-sm ${sel ? 'border-2 border-teal bg-teal text-white font-semibold' : 'border border-[#CCCCCC] bg-white hover:border-charcoal'}">${esc(v.name)}</button>`;
  }).join('');

  $('panel-body').innerHTML = `
  <div class="flex flex-col gap-[22px]">
    <section class="flex flex-col gap-2.5">
      <div class="flex items-center justify-between"><h2 class="${H2}">Your area</h2><span class="text-xs text-muted">${S.mode === 'draw' ? 'Freehand area' : 'Picked points'}</span></div>
      <div class="flex items-baseline gap-2.5"><span class="text-[34px] font-extrabold leading-none">${n}</span><span class="text-[15px] text-charcoal">grid point${n === 1 ? '' : 's'} selected</span></div>
      <p class="m-0 text-sm leading-snug text-charcoal">${n ? (S.capped ? 'Large area: every other NASA grid cell is used so at most ' + S.meta.max_points + ' points are fetched. ' : '') + 'Each dot is one NASA POWER grid cell; sea cells are skipped and land cells averaged with cos(latitude) weights.' : 'Nothing picked yet. Draw around an area on the map, or switch to points.'}</p>
      <div id="pd-status"></div>
      <div class="flex flex-col gap-2 px-3.5 py-3 bg-land rounded-lg">
        <div class="flex items-center justify-between text-[13px] text-charcoal"><span>Years</span><span class="font-semibold text-ink">${y1 - y0 + 1} years</span></div>
        <div class="flex items-center gap-2 text-sm">
          <label class="sr-only" for="y0">First year</label>
          <select id="y0" class="flex-1 min-h-[40px] px-2 rounded-md border border-[#CCCCCC] bg-white">${yearOptions(y0, first, last - S.meta.min_years + 1)}</select>
          <span class="text-muted">to</span>
          <label class="sr-only" for="y1">Last year</label>
          <select id="y1" class="flex-1 min-h-[40px] px-2 rounded-md border border-[#CCCCCC] bg-white">${yearOptions(y1, first + S.meta.min_years - 1, last)}</select>
        </div>
      </div>
    </section>
    <section class="flex flex-col gap-2.5">
      <div class="flex flex-col gap-0.5"><h2 class="${H2}">Most asked here</h2><span class="text-[13px] text-muted">${typeLine}</span></div>
      ${qCards || '<p class="text-sm text-muted m-0">Loading questions…</p>'}
    </section>
    <section class="flex flex-col gap-2.5">
      <h2 class="${H2}">Or pick a variable</h2>
      <div class="flex flex-wrap gap-2">${chips}
        <button type="button" disabled class="min-h-[40px] px-3.5 py-2 rounded-full border border-dashed border-[#B9B9B4] text-muted text-sm">Greenness (NDVI) · later</button>
      </div>
    </section>
    ${S.error ? `<p role="alert" class="m-0 px-3.5 py-3 rounded-lg bg-amber-soft text-amber-ink text-sm">${esc(S.error)}</p>` : ''}
  </div>`;

  const { primary } = chosenVars();
  const name = primary ? S.meta.variables[primary].name : '—';
  const ready = n > 0 && primary && y1 - y0 + 1 >= S.meta.min_years;
  $('panel-foot').innerHTML = `
    <div class="flex flex-col gap-2">
      <span class="text-[13px] text-charcoal">${n} point${n === 1 ? '' : 's'} · ${y0}–${y1} · ${esc(name)}</span>
      <button id="go" type="button" ${ready ? '' : 'disabled'}
        class="flex items-center justify-center gap-2 min-h-[50px] rounded-lg text-base font-bold ${ready ? 'bg-teal text-white hover:bg-teal-dark' : 'bg-[#D9D9D6] text-muted cursor-not-allowed'}">
        Investigate <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M5 12h14M13 6l6 6-6 6"/></svg>
      </button>
    </div>`;

  renderPdStatus();
  // Changing the question/variable recolours the dots by that variable's real values.
  $('panel-body').querySelectorAll('[data-q]').forEach((b) => b.addEventListener('click', () => { S.question = b.dataset.q; S.variable = null; renderPanel(); renderPoints(); }));
  $('panel-body').querySelectorAll('[data-v]').forEach((b) => b.addEventListener('click', () => { S.variable = b.dataset.v; renderPanel(); renderPoints(); }));
  $('y0').addEventListener('change', (e) => { S.years[0] = +e.target.value; if (S.years[1] - S.years[0] + 1 < S.meta.min_years) S.years[1] = Math.min(last, S.years[0] + S.meta.min_years - 1); renderPanel(); });
  $('y1').addEventListener('change', (e) => { S.years[1] = +e.target.value; if (S.years[1] - S.years[0] + 1 < S.meta.min_years) S.years[0] = Math.max(first, S.years[1] - S.meta.min_years + 1); renderPanel(); });
  const go = $('go'); if (go && ready) go.addEventListener('click', investigate);
}

// ---------------------------------------------------------------- investigate
async function investigate() {
  const { primary, linked, why } = chosenVars();
  S.screen = 'loading'; S.error = null;
  renderPanel(); renderPoints();
  try {
    S.result = await api('/api/analyze', { points: [...S.picked.values()], var_id: primary, linked, why, years: S.years });
    S.screen = 'verdict'; S.tab = 'series'; S.view = 'anomaly';
    drawZones();
    loadCrossCheck();
  } catch (err) {
    S.screen = 'pick'; S.error = err.message;
  }
  renderPanel(); renderPoints();
}

// The second dataset (Giovanni) can take a while, so the verdict shows first and this card fills in after.
async function loadCrossCheck() {
  const R = S.result;
  S.cross = { status: 'loading' };
  try {
    const data = await api('/api/crosscheck', { points: [...S.picked.values()], var_id: R.var_id, years: R.years });
    if (S.result === R) S.cross = { status: 'ok', data };
  } catch (err) {
    if (S.result === R) S.cross = { status: 'error', error: err.message };
  }
  if (S.screen === 'verdict' && S.result === R) renderPanel();
}

function crossCard() {
  const C = S.cross;
  const wrap = (cls, icon, title, body) => `<section aria-live="polite" class="flex flex-col gap-2 px-3.5 py-3 rounded-lg border ${cls}">
    <div class="flex items-center gap-2"><span aria-hidden="true">${icon}</span><h2 class="m-0 text-[15px] font-bold text-ink">${title}</h2></div>${body}</section>`;
  if (!C || C.status === 'loading') {
    return wrap('border-line bg-white', '<svg class="animate-spin" width="16" height="16" viewBox="0 0 24 24" fill="none"><circle cx="12" cy="12" r="9" stroke="#E6E6E3" stroke-width="3"/><path d="M21 12a9 9 0 0 0-9-9" stroke="#046460" stroke-width="3" stroke-linecap="round"/></svg>',
      'Cross-checking with a second NASA dataset…', '<p class="m-0 text-[13px] text-muted">Asking Giovanni for the same variable from another instrument. This can take a minute the first time.</p>');
  }
  if (C.status === 'error') return wrap('border-line bg-land', 'ℹ️', 'Cross-check unavailable', `<p class="m-0 text-[13px] text-charcoal">${esc(C.error)}</p>`);
  const D = C.data;
  const look = { agree: ['border-teal-edge bg-teal-soft', '✅'], disagree: ['border-[#F0D9AE] bg-amber-soft', '⚠️'] }[D.state] || ['border-line bg-land', 'ℹ️'];
  const rows = (D.sources || []).map((s) => `<div class="flex justify-between gap-2 text-[13px]"><span class="text-charcoal">${esc(s.label)}</span>
    <span class="font-semibold text-ink whitespace-nowrap">${fmt(s.slope_decade, S.result.variable.decimals ?? 2)} ${esc(S.result.variable.units || '')}/decade · ${esc(s.tier)}</span></div>`).join('');
  return wrap(look[0], look[1], esc(D.headline), `
    <p class="m-0 text-[13px] leading-relaxed text-charcoal">${esc(D.detail)}</p>
    ${rows ? `<div class="flex flex-col gap-1 pt-1 border-t border-line">${rows}</div>` : ''}
    ${D.figure ? '<div id="cross-chart" class="w-full"></div>' : ''}
    ${D.note ? `<p class="m-0 text-[12px] text-muted">${esc(D.note)}</p>` : ''}`);
}

function backToPick() {
  S.screen = 'pick'; S.result = null; S.cross = null;
  zonesLayer.clearLayers();
  if (lasso) lasso.addTo(map);
  renderPanel(); renderPoints();
}

function newCase() {
  S.picked.clear(); S.question = S.questions[0] ? S.questions[0].id : null; S.variable = null;
  if (lasso) { lasso.remove(); lasso = null; }
  backToPick();
  setMode('draw');
}

function drawZones() {
  zonesLayer.clearLayers();
  const z = S.result && S.result.zones;
  if (!z || !z.length) return;
  if (lasso) lasso.remove();
  const vmax = Math.max(...z.map((r) => Math.abs(r.slope_decade || 0))) || 1;
  for (const r of z) {
    const t = (r.slope_decade || 0) / vmax;
    const col = t >= 0 ? mix([244, 243, 239], [194, 65, 12], t) : mix([244, 243, 239], [29, 78, 216], -t);
    const rect = L.rectangle([[r.lat - DLAT / 2, r.lon - DLON / 2], [r.lat + DLAT / 2, r.lon + DLON / 2]],
      { color: '#FFFFFF', weight: 1, fillColor: col, fillOpacity: 0.85 });
    rect.bindTooltip(`${r.lat.toFixed(2)}°, ${r.lon.toFixed(2)}° · ${fmt(r.slope_decade, 3)} per decade${r.significant ? ' · significant (FDR 10%)' : ''}`);
    rect.addTo(zonesLayer);
    if (r.significant) L.circleMarker([r.lat, r.lon], { radius: 3.5, color: '#1F2024', fillColor: '#1F2024', fillOpacity: 1, interactive: false }).addTo(zonesLayer);
  }
}

function mix(a, b, t) {
  t = Math.max(0, Math.min(1, t));
  return `rgb(${a.map((v, i) => Math.round(v + (b[i] - v) * t)).join(',')})`;
}

// ---------------------------------------------------------------- panel: loading + verdict
function renderLoading() {
  const n = S.picked.size;
  $('panel-body').innerHTML = `
    <div class="h-full flex flex-col items-center justify-center gap-4 text-center px-4" role="status" aria-live="polite">
      <svg class="animate-spin" width="40" height="40" viewBox="0 0 24 24" fill="none" aria-hidden="true"><circle cx="12" cy="12" r="9" stroke="#E6E6E3" stroke-width="3"/><path d="M21 12a9 9 0 0 0-9-9" stroke="#046460" stroke-width="3" stroke-linecap="round"/></svg>
      <p class="m-0 text-base font-semibold">Asking NASA POWER for ${n} point${n === 1 ? '' : 's'}…</p>
      <p class="m-0 text-sm text-muted">New points take a few seconds each; points fetched before come from the cache.</p>
    </div>`;
  $('panel-foot').innerHTML = '<button type="button" disabled class="w-full min-h-[50px] rounded-lg bg-[#D9D9D6] text-muted font-bold">Investigating…</button>';
}

const fmt = (v, d) => (v === null || v === undefined ? '–' : (v > 0 ? '+' : '') + Number(v).toFixed(d));
const fmtP = (p) => (p === null || p === undefined ? '–' : p < 0.001 ? '< 0.001' : p.toFixed(3));

function light(title, sub, p) {
  const state = p < 0.05 ? 'ok' : p < 0.10 ? 'maybe' : 'no';
  const box = { ok: 'bg-teal-soft border-teal-edge', maybe: 'bg-amber-soft border-[#F0D9AE]', no: 'bg-land border-line' }[state];
  const ink = { ok: 'text-teal-dark', maybe: 'text-amber-ink', no: 'text-charcoal' }[state];
  const icon = {
    ok: '<path d="M5 12l5 5 9-10"/>',
    maybe: '<path d="M5 12h14"/>',
    no: '<path d="M6 6l12 12M18 6L6 18"/>',
  }[state];
  return `<div class="flex flex-col gap-1 px-3 py-2.5 rounded-lg border ${box}">
    <span class="flex items-center gap-1.5 text-[13px] font-bold ${ink}"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${icon}</svg>${title}</span>
    <span class="text-xs text-charcoal">${sub} · p ${fmtP(p).startsWith('<') ? fmtP(p) : '= ' + fmtP(p)}</span></div>`;
}

function renderVerdict() {
  const R = S.result, r = R.res, v = R.variable, d = v.decimals ?? 2, u = v.units || '';
  const stamp = { significant: ['Significant trend', 'border-teal text-teal'], suggestive: ['Possible trend', 'border-[#B7791F] text-amber-ink'], none: ['No clear trend yet', 'border-charcoal text-charcoal'] }[r.tier];
  const [lo, hi] = r.ci_decade;
  const m = Math.max(Math.abs(lo), Math.abs(hi), Math.abs(r.slope_decade)) * 1.25 || 1;
  const pos = (x) => ((x + m) / (2 * m)) * 100;
  const total = r.total_change;
  const spanTxt = Math.round(r.span_years);
  const chg = r.tier !== 'none' && total !== null
    ? `About ${fmt(total, d)} ${esc(u)} over the ${spanTxt} years since ${R.years[0]}${r.pct_decade !== null ? ` (${fmt(r.pct_decade, 1)}% of the average per decade)` : ''}. This shows a change, not its cause.`
    : esc(R.words.detail);
  const tabs = [['series', 'Time series'], ['zones', 'Zones'], ['evidence', 'Evidence'], ['method', 'Method']].map(([id, label]) =>
    `<button type="button" role="tab" data-tab="${id}" aria-selected="${S.tab === id}" class="min-h-[44px] px-3 -mb-px text-sm border-b-[3px] ${S.tab === id ? 'border-teal text-teal font-bold' : 'border-transparent text-charcoal hover:text-ink'}">${label}</button>`).join('');

  let tabBody = '';
  if (S.tab === 'series') {
    tabBody = `<div class="flex flex-col gap-2">
      <div id="chart" class="w-full"></div>
      <div class="flex gap-1.5">
        ${[['anomaly', 'Anomalies'], ['raw', 'Raw values']].map(([id, label]) => `<button type="button" data-view="${id}" aria-pressed="${S.view === id}" class="min-h-[36px] px-3 rounded-full text-[13px] ${S.view === id ? 'border-2 border-teal bg-teal text-white' : 'border border-[#CCCCCC] bg-white'}">${label}</button>`).join('')}
      </div>
      <p class="m-0 text-[13px] text-charcoal">Record: ${esc(r.start)} to ${esc(r.end)} · ${r.n_months} months · ${r.missing_months} missing · ${R.points_used} of ${R.points.length} points are land</p>
      ${r.tier !== 'significant' && r.years_to_significance !== null && r.years_to_significance <= 50 ? `<p class="m-0 text-[13px] text-charcoal">If this rate held, about ${Math.round(r.years_to_significance)} more years of data would be needed to be sure.</p>` : ''}
    </div>`;
  } else if (S.tab === 'zones') {
    const z = R.zones;
    tabBody = z && z.length
      ? `<div class="flex flex-col gap-2.5 text-sm text-charcoal leading-relaxed">
          <p class="m-0">Each square on the map is one grid point, tested on its own. Orange rising, blue falling; a dot means it survives the correction for testing ${z.length} points at once (Benjamini-Hochberg, 10%).</p>
          <p class="m-0 px-3.5 py-2.5 bg-land rounded-lg">Significant: ${z.filter((x) => x.significant && x.slope_decade > 0).length} rising, ${z.filter((x) => x.significant && x.slope_decade < 0).length} falling, ${z.filter((x) => !x.significant).length} without a clear trend.</p></div>`
      : `<p class="m-0 text-sm text-charcoal leading-relaxed">${R.points_used < 2 ? 'Pick at least two land points to compare zones.' : 'The per-point zone map arrives with step 5 (trend_grid). Until then the map shows which picked points were land and which were sea.'}</p>`;
  } else if (S.tab === 'evidence') {
    const L_ = R.link;
    tabBody = `<div class="flex flex-col gap-3 text-sm leading-relaxed text-charcoal">
      <div class="px-3.5 py-3 border border-line rounded-lg"><strong class="text-ink">${esc(v.name)}</strong><br>${esc(v.definition || '')}${v.source ? `<br><span class="text-muted">Source: ${esc(v.source)}</span>` : ''}${v.caveat ? `<br><span class="text-muted">Caveat: ${esc(v.caveat)}</span>` : ''}</div>
      ${L_ ? `<div class="px-3.5 py-3 border border-line rounded-lg"><strong class="text-ink">Checked against ${esc(L_.name.toLowerCase())}</strong><br>${esc(L_.why)}<br>${L_.r === null ? 'Not enough overlapping months to compare.' : `Month-to-month anomalies move together with r = ${fmt(L_.r, 2)} (${L_.n} months). A link like this is consistent with a connection; it is not proof of cause.`}</div>` : ''}
    </div>`;
  } else {
    tabBody = `<ol class="m-0 pl-5 flex flex-col gap-2 text-sm leading-snug text-charcoal list-decimal">
      <li>NASA POWER monthly values at each picked grid point; sea points skipped, land averaged by cos(latitude).</li>
      <li>Anomalies: each month minus its usual value, so seasons don't look like trends.</li>
      <li>Rate per decade from a straight-line fit with Newey-West errors (t-test, 95% range).</li>
      <li>Mann-Kendall (Hamed-Rao) and Sen's slope as a second, rank-based test.</li>
      <li>Significant only when both tests give p &lt; 0.05 and agree on direction; possible when either gives p &lt; 0.10.</li>
    </ol>`;
  }

  $('panel-body').innerHTML = `
  <div class="flex flex-col gap-3.5">
    <nav aria-label="Case" class="flex flex-wrap gap-1.5 text-[13px]">
      ${[`${R.points.length} point${R.points.length === 1 ? '' : 's'}`, v.name, `${R.years[0]}–${R.years[1]}`].map((t) => `<button type="button" data-back class="px-2.5 py-1 rounded-full bg-land hover:bg-[#E9E8E3]">${esc(t)}</button>`).join('')}
    </nav>
    <div class="flex flex-col gap-2.5">
      <h1 class="m-0 text-[26px] leading-tight font-extrabold text-ink">${esc(R.words.headline)}</h1>
      <span class="self-start text-xs font-extrabold tracking-[1.2px] px-2.5 py-1 border-2 rounded-full uppercase ${stamp[1]}">${stamp[0]}</span>
      <p class="m-0 text-[15px] leading-relaxed text-charcoal">${chg}</p>
    </div>
    <div class="grid grid-cols-2 gap-2">
      ${light('Straight-line test', 'OLS, Newey-West', r.p_ttest)}
      ${light('Rank test', 'Mann-Kendall', r.p_mk)}
    </div>
    <div class="flex flex-col gap-1.5">
      <div class="flex justify-between text-[13px] text-charcoal"><span>95% range of the rate</span><span class="font-semibold text-ink">${fmt(lo, d)} to ${fmt(hi, d)} ${esc(u)} / decade</span></div>
      <div class="relative h-3.5 bg-land rounded-full">
        <div class="absolute top-0 bottom-0 rounded-full ${r.slope_decade >= 0 ? 'bg-[#F6C8A6]' : 'bg-[#BFD0F7]'}" style="left:${pos(lo)}%;width:${pos(hi) - pos(lo)}%"></div>
        <div class="absolute -top-[3px] w-[3px] h-5 bg-[#6B6B66]" style="left:${pos(0)}%"></div>
        <div class="absolute -top-[3px] w-1 h-5 rounded ${r.slope_decade >= 0 ? 'bg-rise' : 'bg-fall'}" style="left:calc(${pos(r.slope_decade)}% - 2px)"></div>
      </div>
      <div class="flex justify-between text-[11px] text-muted"><span>${fmt(-m, d)}</span><span>0 · Sen's slope ${fmt(r.sen_decade, d)}</span><span>${fmt(m, d)}</span></div>
    </div>
    ${crossCard()}
    <div role="tablist" aria-label="Details" class="flex gap-1 border-b border-[#E6E6E3]">${tabs}</div>
    <div>${tabBody}</div>
  </div>`;

  $('panel-foot').innerHTML = `
    <div class="flex gap-2">
      <button id="csv" type="button" class="flex-1 min-h-[46px] rounded-lg border border-[#CCCCCC] bg-white text-sm font-semibold hover:border-charcoal">Data CSV</button>
      <button id="back" type="button" class="flex-1 min-h-[46px] rounded-lg border border-[#CCCCCC] bg-white text-sm font-semibold hover:border-charcoal">Back</button>
      <button id="new" type="button" class="flex-[1.3] min-h-[46px] rounded-lg bg-charcoal text-white text-sm font-bold hover:bg-ink">New case</button>
    </div>
    <p class="mt-2 mb-0 text-[11px] text-muted">SI-assisted: parts of this app were drafted with Claude (Anthropic) and reviewed by the team.</p>`;

  $('panel-body').querySelectorAll('[data-tab]').forEach((b) => b.addEventListener('click', () => { S.tab = b.dataset.tab; renderPanel(); }));
  $('panel-body').querySelectorAll('[data-view]').forEach((b) => b.addEventListener('click', () => { S.view = b.dataset.view; renderPanel(); }));
  $('panel-body').querySelectorAll('[data-back]').forEach((b) => b.addEventListener('click', backToPick));
  $('back').addEventListener('click', backToPick);
  $('new').addEventListener('click', newCase);
  $('csv').addEventListener('click', downloadCsv);
  if (S.tab === 'series') {
    const fig = R.figures[S.view];
    Plotly.react('chart', fig.data, { ...fig.layout, autosize: true }, { displayModeBar: false, responsive: true });
  }
  if (S.cross && S.cross.status === 'ok' && S.cross.data.figure && $('cross-chart')) {
    const cf = S.cross.data.figure;
    Plotly.react('cross-chart', cf.data, { ...cf.layout, autosize: true }, { displayModeBar: false, responsive: true });
  }
}

function downloadCsv() {
  const R = S.result;
  const rows = [`month,${R.var_id}`].concat(R.series.month.map((m, i) => `${m},${R.series.value[i] ?? ''}`));
  const blob = new Blob([rows.join('\n')], { type: 'text/csv' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = `trend_detective_${R.var_id}_${R.years[0]}_${R.years[1]}.csv`;
  a.click();
  URL.revokeObjectURL(a.href);
}

function renderPanel() {
  if (!S.meta) return;
  if (!flashTimer) updateHint();
  if (S.screen === 'loading') return renderLoading();
  if (S.screen === 'verdict') return renderVerdict();
  return renderPick();
}

// ---------------------------------------------------------------- boot
$('tool-draw').addEventListener('click', () => setMode('draw'));
$('tool-points').addEventListener('click', () => setMode('points'));
$('tool-clear').addEventListener('click', () => { if (S.screen !== 'pick') return; S.picked.clear(); if (lasso) { lasso.remove(); lasso = null; } selectionChanged(); });
$('tool-home').addEventListener('click', () => map.setView([34.2, 9.6], 6));
map.on('moveend', () => { if (S.mode === 'points') renderPoints(); });

(async function boot() {
  try {
    S.meta = await api('/api/meta');
    S.years = [...S.meta.years];
  } catch (err) {
    $('panel-body').innerHTML = `<p role="alert" class="text-sm">Could not reach the server: ${esc(err.message)}</p>`;
    return;
  }
  setMode('draw');
  renderPanel();
  loadQuestions();
})();
