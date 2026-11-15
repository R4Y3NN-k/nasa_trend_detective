// SI-assisted: parts of this file were drafted with Claude (Anthropic) and reviewed by the team
// Trend Detective map-first UI. Owner: C (dashboard). Talks to web/server.py; grid maths in grid.js.
'use strict';

const G = window.TDGrid;
const { DLAT, DLON, snap, keyOf, cellsIn } = G;
const K_MIN = 4;              // fewest land cells worth analysing (groups and uplands need four)

// ---------------------------------------------------------------- state
const S = {
  meta: null,
  ui: 'simple',               // 'simple' | 'expert': same verdict and numbers, Expert adds depth
  mode: 'pan',                // map tool: 'pan' | 'draw' | 'points'
  picked: new Map(),          // key -> [lat, lon]
  added: new Set(),           // keys the app added itself (nearest land cells), drawn dashed
  note: null,                 // plain sentence about what the app did to the selection
  history: [],                // undo stack of selections
  questions: [], climate: null, climateSig: null,
  userChose: false, question: null, variable: null,
  years: [1981, 2025],
  screen: 'pick',             // 'pick' | 'loading' | 'verdict'
  result: null, error: null,
  cross: null, explain: null, seasons: null, scan: null, groups: null,
  tab: 'series', view: 'anomaly', groupView: '2d', mapGroups: false,
  capped: false, widened: false,
  pd: new Map(),              // key -> NASA POWER data for that cell: {status, land, means, ...}
  isLand: null,               // (lat, lon) -> bool from the bundled land outline, once loaded
  place: null,                // last place chosen in the search box
};

const RAMPS = {               // light = low, dark = high, for the real per-cell means
  T2M: [[253, 231, 212], [194, 65, 12]], PRECTOTCORR: [[220, 232, 251], [29, 78, 216]], GWETTOP: [[237, 227, 209], [4, 100, 96]],
  T2M_MAX: [[254, 226, 204], [153, 27, 27]], T2M_MIN: [[219, 234, 254], [194, 65, 12]], FROST_DAYS: [[224, 242, 254], [12, 74, 110]],
  PRECSNOLAND: [[241, 245, 249], [30, 64, 175]], SNODP: [[241, 245, 249], [30, 64, 175]], RH2M: [[236, 253, 245], [6, 95, 70]],
};

const GLOSSARY = {
  trend: 'A steady rise or fall over many years, beyond the usual ups and downs.',
  anomaly: 'How far a month is from what is usual for that calendar month here. It removes the seasons.',
  decade: 'Per decade = the change over ten years if the trend stays the same.',
  range: 'We are 95% confident the true rate lies in this range. If it includes zero, there may be no trend.',
  fdr: 'When many cells are tested at once, some look significant by luck. This correction keeps such false alarms under 10%.',
};

// ---------------------------------------------------------------- small helpers
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const $ = (id) => document.getElementById(id);
const fmt = (v, d) => (v === null || v === undefined ? '–' : (v > 0 ? '+' : v < 0 ? '−' : '') + Math.abs(Number(v)).toFixed(d));
const fmtP = (p) => (p === null || p === undefined ? '–' : p < 0.001 ? '< 0.001' : p.toFixed(3));
const plural = (n, word) => `${n} ${word}${n === 1 ? '' : 's'}`;
const term = (key, text) => `<button type="button" class="term" data-def="${esc(GLOSSARY[key])}">${text}</button>`;
const mix = (a, b, t) => { t = Math.max(0, Math.min(1, t)); return `rgb(${a.map((v, i) => Math.round(v + (b[i] - v) * t)).join(',')})`; };

const ICONS = {
  up: '<path d="M7 17L17 7"/><path d="M9 7h8v8"/>', down: '<path d="M7 7l10 10"/><path d="M17 9v8H9"/>', flat: '<path d="M5 12h14"/>',
  check: '<path d="M5 12l5 5 9-10"/>', info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 7.5v.5"/>',
  chev: '<path d="M9 6l6 6-6 6"/>', back: '<path d="M19 12H5"/><path d="M11 6l-6 6 6 6"/>', next: '<path d="M5 12h14"/><path d="M13 6l6 6-6 6"/>',
  link: '<path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1"/><path d="M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1"/>',
  save: '<path d="M12 4v11"/><path d="M7 11l5 5 5-5"/><path d="M5 20h14"/>',
  print: '<path d="M7 8V4h10v4"/><path d="M7 17H5a2 2 0 0 1-2-2v-4a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2v4a2 2 0 0 1-2 2h-2"/><path d="M7 14h10v6H7z"/>',
  layers: '<path d="M12 3l9 5-9 5-9-5 9-5z"/><path d="M3 13l9 5 9-5"/>', hill: '<path d="M3 19l6-10 4 6 2-3 6 7z"/>',
  spin: '<path d="M21 12a9 9 0 1 1-9-9"/>',
};
const ic = (name, cls = '') => `<svg class="ico ${cls}" viewBox="0 0 24 24" aria-hidden="true">${ICONS[name]}</svg>`;

// Preferences survive a reload when the browser allows storage; the app works the same without it.
const pref = {
  get(k, d) { try { return localStorage.getItem('td.' + k) ?? d; } catch (_) { return d; } },
  set(k, v) { try { localStorage.setItem('td.' + k, v); } catch (_) { /* private mode: fine */ } },
};

async function api(path, body) {
  const resp = await fetch(path, body === undefined ? {} : {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
  });
  const data = await resp.json().catch(() => ({ error: 'The server sent an unreadable answer.' }));
  if (!resp.ok) throw new Error(data.error || `Server error ${resp.status}`);
  return data;
}

// Direction and certainty in words, with an icon: colour is only the third signal.
function statusOf(tier, slope) {
  if (tier === 'none' || !slope) return { cls: 'flat', icon: 'flat', words: 'No clear change yet' };
  const up = slope > 0;
  return { cls: (up ? 'up' : 'down') + (tier === 'suggestive' ? ' maybe' : ''), icon: up ? 'up' : 'down',
    words: `${tier === 'significant' ? 'Clearly' : 'Possibly'} ${up ? 'rising' : 'falling'}` };
}

// ---------------------------------------------------------------- map
const map = L.map('map', {
  zoomControl: false, attributionControl: true, minZoom: 2,
  zoomSnap: 0.25, zoomDelta: 0.5, wheelPxPerZoomLevel: 90, wheelDebounceTime: 20,
  inertia: true, inertiaDeceleration: 4000, inertiaMaxSpeed: 1500, easeLinearity: 0.25, worldCopyJump: true,
  keyboard: true, keyboardPanDelta: 120, boxZoom: false,
}).setView([34.2, 9.6], 6);
L.control.zoom({ position: 'topleft' }).addTo(map);
L.tileLayer('https://{s}.tile.openstreetmap.fr/hot/{z}/{x}/{y}.png', {
  maxZoom: 18, subdomains: 'abc',
  attribution: '© OpenStreetMap contributors, tiles HOT · data NASA POWER (MERRA-2)',
}).addTo(map);

const pointsLayer = L.layerGroup().addTo(map);
const zonesLayer = L.layerGroup().addTo(map);
let lasso = null;
const reduceMotion = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
const phone = () => window.innerWidth <= 820;
const mapPadding = () => (phone() ? { paddingTopLeft: [60, 70], paddingBottomRight: [20, Math.round(window.innerHeight * 0.56)] }
  : { paddingTopLeft: [80, 70], paddingBottomRight: [470, 70] });

function setMode(mode) {
  S.mode = mode;
  const drawing = mode === 'draw';
  map.getContainer().classList.toggle('drawing', drawing);
  if (drawing) map.dragging.disable(); else map.dragging.enable();
  for (const [id, on] of [['tool-pan', mode === 'pan'], ['tool-draw', drawing], ['tool-points', mode === 'points']]) $(id).setAttribute('aria-pressed', String(on));
  updateHint();
  renderPoints();
}

function updateHint() {
  const text = $('hint-text'), act = $('hint-action');
  act.hidden = true;
  if (S.screen === 'verdict') {
    const groups = S.tab === 'groups' && S.mapGroups;
    text.innerHTML = groups ? 'Each colour is a group of cells that change alike'
      : S.result && S.result.zones && S.result.zones.length
        ? '<span class="legend-sw" style="background:#C2410C"></span>rising<span class="legend-sw" style="background:#1D4ED8"></span>falling · a dot marks a clear trend at that cell'
        : 'The cells used for this verdict';
  } else if (S.screen === 'loading') text.textContent = 'Fetching NASA POWER data…';
  else if (S.place && S.placeFresh) {
    text.textContent = `${S.place.name}: draw a loop, or`;
    act.textContent = 'Investigate this area'; act.hidden = false;
  } else if (S.mode === 'draw') text.textContent = 'Draw one loop around your area · Esc to cancel';
  else if (S.mode === 'points') text.textContent = `Tap grid cells to add or remove them (up to ${S.meta ? S.meta.max_points : 30})`;
  else text.textContent = phone() ? 'Pen tool: draw a loop around an area' : 'Drag to move · pen tool or Shift + drag to draw a loop around an area';
}

let flashTimer = null;
function flash(msg) {
  $('hint-text').textContent = msg; $('hint-action').hidden = true;
  clearTimeout(flashTimer);
  flashTimer = setTimeout(() => { flashTimer = null; updateHint(); }, 2600);
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
  const zoned = S.screen === 'verdict' && S.result && S.result.zones && S.result.zones.length;
  for (const [key, [lat, lon]] of show) {
    const on = S.picked.has(key), d = S.pd.get(key);
    if (zoned && d && d.status === 'ok' && d.land) continue;   // the zone squares already show these cells
    let style;
    if (!on) style = { radius: 4, color: '#1B2A8C', weight: 1.5, fillColor: '#FFFFFF', fillOpacity: 1 };
    else if (d && d.status === 'ok' && !d.land) style = { radius: 6, color: '#5A5B60', weight: 2, fillColor: '#FFFFFF', fillOpacity: 1, dashArray: '2 3' };
    else if (d && d.status === 'ok') style = { radius: 8, color: '#FFFFFF', weight: 2, fillColor: ramp.color(d.means[ramp.var]), fillOpacity: 1 };
    else if (d && d.status === 'error') style = { radius: 6, color: '#B42318', weight: 2.5, fillColor: '#FFFFFF', fillOpacity: 1 };
    else style = { radius: 6, color: '#046460', weight: 2, fillColor: '#FFFFFF', fillOpacity: 1, dashArray: d && d.status === 'loading' ? '3 3' : null };
    if (on && S.added.has(key)) {   // cells the app added itself: a dashed ring says so
      L.circleMarker([lat, lon], { radius: 13, color: '#1F2024', weight: 1.5, dashArray: '4 4', fill: false, interactive: false }).addTo(pointsLayer);
    }
    const m = L.circleMarker([lat, lon], { ...style, interactive: on || (S.mode === 'points' && S.screen === 'pick') });
    m.bindTooltip(on ? pointTooltip(lat, lon, d, key) : `${lat.toFixed(2)}°, ${lon.toFixed(2)}° · tap to add`, { direction: 'top' });
    m.on('click', () => {
      if (S.mode !== 'points' || S.screen !== 'pick') return;
      if (!S.picked.has(key) && S.picked.size >= cap) { flash(`At most ${cap} cells: NASA POWER is asked once per cell.`); return; }
      pushHistory();
      if (S.picked.has(key)) { S.picked.delete(key); S.added.delete(key); } else S.picked.set(key, [lat, lon]);
      if (lasso) { lasso.remove(); lasso = null; }
      S.note = null; S.capped = false;
      selectionChanged();
    });
    m.addTo(pointsLayer);
  }
}

// Freehand lasso on the map container: pen tool, or Shift + drag from any tool.
(function setupLasso() {
  const el = map.getContainer();
  let drawing = false, path = [], line = null;
  el.addEventListener('pointerdown', (e) => {
    if ((S.mode !== 'draw' && !e.shiftKey) || S.screen !== 'pick' || e.button !== 0) return;
    if (e.target.closest('.leaflet-control')) return;
    if (S.mode !== 'draw') map.dragging.disable();
    drawing = true;
    path = [map.mouseEventToLatLng(e)];
    line = L.polyline(path, { color: '#046460', weight: 3, dashArray: '8 6', interactive: false }).addTo(map);
    try { el.setPointerCapture(e.pointerId); } catch (_) { /* pen/synthetic pointers: drawing still works */ }
    e.preventDefault();
  });
  el.addEventListener('pointermove', (e) => {
    if (!drawing) return;
    const ll = map.mouseEventToLatLng(e);
    if (map.latLngToContainerPoint(path[path.length - 1]).distanceTo(map.latLngToContainerPoint(ll)) < 4) return;
    path.push(ll);
    line.setLatLngs(path);
  });
  const finish = () => {
    if (!drawing) return;
    drawing = false;
    line.remove();
    if (S.mode !== 'draw') map.dragging.enable();
    if (path.length < 5) return;
    pushHistory();
    setLasso(path.map((p) => [p.lat, p.lng]));
    selectLoop(path.map((p) => [p.lat, p.lng]));
    if (S.mode === 'draw') setMode('pan');
  };
  el.addEventListener('pointerup', finish);
  el.addEventListener('pointercancel', finish);
  window.cancelLasso = () => { if (drawing) { drawing = false; line.remove(); } };
})();

function setLasso(latlngs) {
  if (lasso) { lasso.remove(); lasso = null; }
  if (latlngs && latlngs.length) {
    lasso = L.polygon(latlngs, { color: '#046460', weight: 3, dashArray: '10 6', fillColor: '#046460', fillOpacity: 0.1, interactive: false }).addTo(map);
  }
}

// ---------------------------------------------------------------- selection: loop -> NASA grid cells
// Land cells inside the loop; when there are fewer than K_MIN, the nearest land cells are added (ring search
// on the grid, see grid.js) and the person is told. With the land outline loaded, sea cells are never fetched.
function selectLoop(loop) {
  const lats = loop.map((p) => p[0]), lons = loop.map((p) => p[1]);
  const ring = loop.map((p) => [p[1], p[0]]);
  const cap = S.meta ? S.meta.max_points : 30;
  const centre = [(Math.min(...lats) + Math.max(...lats)) / 2, (Math.min(...lons) + Math.max(...lons)) / 2];
  const at = (stride) => cellsIn(Math.min(...lats), Math.min(...lons), Math.max(...lats), Math.max(...lons), stride)
    .filter(([lat, lon]) => G.inRing(lon, lat, ring));
  const inLoop = at(1);
  const land = S.isLand ? inLoop.filter((c) => S.isLand(c[0], c[1])) : inLoop;
  S.added = new Set(); S.note = null; S.capped = false; S.widened = false;

  let cells;
  if (land.length >= K_MIN || !S.isLand) {
    let stride = 1;
    cells = land.length ? land : [snap(centre[0], centre[1])];
    while (cells.length > cap) { stride++; cells = at(stride).filter((c) => !S.isLand || S.isLand(c[0], c[1])); }
    S.capped = stride > 1;
  } else {
    // Small or coastal loop. Keep its own cells when there are only a few (the coarse outline misses small
    // islands; NASA's data then decides land or sea), and top up with the nearest land cells.
    cells = inLoop.length <= 6 ? [...inLoop] : [...land];
    const have = new Set(cells.map((c) => keyOf(c[0], c[1])));
    let landCount = land.length;
    for (const c of G.nearestLandCells(centre[0], centre[1], K_MIN + cells.length, S.isLand, 3)) {
      if (landCount >= K_MIN) break;
      const key = keyOf(c[0], c[1]);
      if (have.has(key)) continue;
      cells.push(c); have.add(key); S.added.add(key); landCount++;
    }
    if (!cells.length) cells = [snap(centre[0], centre[1])];
    if (S.added.size) {
      const nearest = `the ${plural(S.added.size, 'nearest land cell')}, shown with a dashed ring`;
      S.note = !inLoop.length && !S.isLand(centre[0], centre[1]) ? `There is no land inside your loop, so we used ${nearest}.`
        : !inLoop.length ? `Your loop was smaller than one NASA grid cell (about 55 km), so we used ${nearest}.`
          : `Your loop held fewer than ${K_MIN} land cells, so we added ${nearest}.`;
    }
  }
  S.picked = new Map(cells.map(([lat, lon]) => [keyOf(lat, lon), [lat, lon]]));
  selectionChanged();
}

// A box of about 2° x 2° around a place from the search box.
function selectAround(place) {
  pushHistory();
  const b = [[place.lat - 1, place.lon - 1], [place.lat - 1, place.lon + 1], [place.lat + 1, place.lon + 1], [place.lat + 1, place.lon - 1]];
  setLasso(b);
  selectLoop(b);
  if (reduceMotion || document.hidden) map.fitBounds(L.latLngBounds(b).pad(0.35), { ...mapPadding(), animate: false }); else map.flyToBounds(L.latLngBounds(b).pad(0.35), { ...mapPadding(), duration: 0.8 });
}

// Every picked cell turned out to be sea (NASA's own data says so): use the nearest land cells instead of an error.
function widenIfAllSea() {
  const c = pdCounts();
  if (S.screen !== 'pick' || S.widened || !c.total || c.pending || c.land || !c.sea) return;
  S.widened = true;
  const cells = [...S.picked.values()];
  const centre = [cells.reduce((a, p) => a + p[0], 0) / cells.length, cells.reduce((a, p) => a + p[1], 0) / cells.length];
  const known = (lat, lon) => { const d = S.pd.get(keyOf(lat, lon)); return d && d.status === 'ok' ? d.land : (S.isLand ? S.isLand(lat, lon) : true); };
  const near = G.nearestLandCells(centre[0], centre[1], K_MIN, known, 3);
  if (!near.length) return;
  for (const [lat, lon] of near) { S.picked.set(keyOf(lat, lon), [lat, lon]); S.added.add(keyOf(lat, lon)); }
  S.note = `Every cell in your loop is sea, so we used the ${plural(near.length, 'nearest land cell')}, shown with a dashed ring.`;
  selectionChanged();
}

function pushHistory() {
  S.history.push({ cells: [...S.picked.values()], added: [...S.added], note: S.note, capped: S.capped,
    lasso: lasso ? lasso.getLatLngs()[0].map((ll) => [ll.lat, ll.lng]) : null });
  if (S.history.length > 30) S.history.shift();
}

function undo() {
  if (S.screen !== 'pick' || !S.history.length) return;
  const h = S.history.pop();
  S.picked = new Map(h.cells.map(([lat, lon]) => [keyOf(lat, lon), [lat, lon]]));
  S.added = new Set(h.added); S.note = h.note; S.capped = h.capped; S.widened = true;
  setLasso(h.lasso);
  selectionChanged();
}

let areaTimer = null;
function selectionChanged() {
  S.climate = null; S.climateSig = null; S.error = null; S.placeFresh = false;
  $('tool-undo').disabled = !S.history.length;
  queuePointData();
  renderPoints();
  renderPanel();
  updateHash();
  clearTimeout(areaTimer);
  areaTimer = setTimeout(loadQuestions, 250);
}

async function loadQuestions() {
  try {
    const data = await api('/api/area', { points: [...S.picked.values()] });
    if (S.climate) return;                    // the climate-ranked list is already in
    S.questions = data.questions;
    adoptQuestion();
  } catch (err) { S.error = err.message; }
  if (S.screen === 'pick') renderPanel();
}

// Keep the person's own choice; otherwise select the top question for this place.
function adoptQuestion() {
  if (S.restoreQ && S.questions.some((q) => q.id === S.restoreQ)) { S.question = S.restoreQ; S.variable = null; S.restoreQ = null; return; }
  if (S.variable) return;
  if (!S.userChose || !S.questions.some((q) => q.id === S.question)) S.question = S.questions[0] ? S.questions[0].id : null;
  if (S.screen === 'pick') updateHash();
}

// ---------------------------------------------------------------- real NASA POWER data per picked cell
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
    if (!S.picked.has(key)) { S.pd.delete(key); continue; }
    pdActive++;
    S.pd.set(key, { status: 'loading' });
    api('/api/point', { lat, lon })
      .then((d) => S.pd.set(key, { status: 'ok', ...d }))
      .catch((err) => S.pd.set(key, { status: 'error', error: err.message }))
      .finally(() => { pdActive--; pdChanged(); pumpPointData(); setTimeout(afterPointData, 0); });   // not via rAF: hidden tabs pause it
  }
  pdChanged();
}

// Runs on a timer, not an animation frame, so it also updates a tab that is in the background.
function afterPointData() { widenIfAllSea(); renderPoints(); patch('sec-area', areaHtml()); syncGo(); maybeScan(); maybeClimate(); }

function pdChanged() {
  if (pdFrame) return;
  pdFrame = requestAnimationFrame(() => { pdFrame = 0; renderPoints(); patch('sec-area', areaHtml()); syncGo(); });
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
  return { var: vid, min, max, n: vals.length, lo, hi,
    color: (v) => (v === null || v === undefined ? '#9A9B9F' : mix(lo, hi, max > min ? (v - min) / (max - min) : 0.6)) };
}

function valueText(vid, v) {
  const info = (S.meta && S.meta.variables[vid]) || { units: '', decimals: 2 };
  return v === null || v === undefined ? '–' : `${Number(v).toFixed(info.decimals ?? 2)} ${info.units || ''}`.trim();
}

function pointTooltip(lat, lon, d, key) {
  const head = `<strong>NASA POWER cell ${lat.toFixed(2)}°, ${lon.toFixed(2)}°</strong>`;
  const extra = S.added.has(key) ? '<br>Added by the app: nearest land cell' : '';
  if (!d || d.status === 'queued') return `${head}<br>Waiting to load…${extra}`;
  if (d.status === 'loading') return `${head}<br>Loading from NASA POWER…${extra}`;
  if (d.status === 'error') return `${head}<br>Could not load: ${esc(d.error)}`;
  if (!d.land) return `${head}<br>Sea: left out of the average`;
  const rows = Object.keys(S.meta.variables).filter((v) => v in d.means)
    .map((v) => `${esc(S.meta.variables[v].name)}: <strong>${esc(valueText(v, d.means[v]))}</strong>`).join('<br>');
  const elev = d.elevation_m !== null && d.elevation_m !== undefined ? ` · ${Math.round(d.elevation_m)} m` : '';
  return `${head} · land${elev}<br>${rows}<br><span style="color:#5A5B60">Mean ${d.first} to ${d.last} · ${d.months} months</span>${extra}`;
}

// ---------------------------------------------------------------- climate-aware questions and the quick scan
let climateTimer = null;
function maybeClimate() {
  if (S.screen !== 'pick') return;
  const loaded = [...S.picked.keys()].filter((k) => { const d = S.pd.get(k); return d && d.status === 'ok' && d.land; });
  if (!loaded.length) return;
  const sig = loaded.sort().join('|');
  if (S.climateSig === sig) return;
  S.climateSig = sig;
  clearTimeout(climateTimer);
  climateTimer = setTimeout(async () => {
    const sum = {}, wsum = {};
    for (const k of loaded) {
      const d = S.pd.get(k), w = Math.cos(d.lat * Math.PI / 180);
      for (const [v, x] of Object.entries(d.means || {})) {
        if (x === null || x === undefined) continue;
        sum[v] = (sum[v] || 0) + w * x; wsum[v] = (wsum[v] || 0) + w;
      }
    }
    const means = Object.fromEntries(Object.keys(sum).map((v) => [v, sum[v] / wsum[v]]));
    try {
      const d = await api('/api/climate', { means });
      if (S.climateSig !== sig || S.screen !== 'pick' || !d.questions || !d.questions.length) return;
      S.questions = d.questions; S.climate = d.climate;
      adoptQuestion();
      renderPanel(); renderPoints();
    } catch (_) { /* the full scan will still set the questions */ }
  }, 150);
}

const scanSig = () => `${[...S.picked.keys()].sort().join('|')}#${S.years.join('-')}`;

function maybeScan() {
  const c = pdCounts();
  if (!c.total || c.pending || !c.land || S.screen !== 'pick') return;
  const sig = scanSig();
  if (S.scan && S.scan.sig === sig) return;
  S.scan = { sig, status: 'loading' };
  api('/api/scan', { points: [...S.picked.values()], years: S.years })
    .then((d) => {
      if (!S.scan || S.scan.sig !== sig) return;
      S.scan = { sig, status: 'ok', data: d.scan };
      if (d.questions && d.questions.length) { S.questions = d.questions; S.climate = d.climate; adoptQuestion(); }
    })
    .catch((err) => { if (S.scan && S.scan.sig === sig) S.scan = { sig, status: 'error', error: err.message }; })
    .finally(() => { if (S.screen === 'pick') renderPanel(); });
}

function scanStatus(vid) {
  const s = S.scan && S.scan.status === 'ok' && S.scan.sig === scanSig() ? S.scan.data.find((x) => x.var_id === vid) : null;
  if (!s) return S.scan && S.scan.status === 'loading' ? '<span class="skel w40" style="margin-top:6px"></span>' : '';
  const st = statusOf(s.tier, s.direction === 'falling' ? -1 : 1);
  return `<span class="status ${st.cls}">${ic(st.icon, 's')}${st.words}<span class="rate num">· ${esc(s.rate_per_decade)} per decade</span></span>`;
}

function chosenVars() {
  if (S.variable) return { primary: S.variable, linked: null, why: '' };
  const q = S.questions.find((x) => x.id === S.question);
  return q ? { primary: q.primary, linked: q.linked, why: q.why } : { primary: null, linked: null, why: '' };
}

// ---------------------------------------------------------------- panel: shared shell
function patch(id, html) {            // replace one section without redrawing the rest (keeps scroll and open details)
  const el = $(id);
  if (el) el.outerHTML = html;
}

function headHtml() {
  const left = S.screen === 'verdict'
    ? `<button type="button" class="link" data-act="back">${ic('back', 's')}Change area or question</button>`
    : '<span class="where">NASA data, 1981 to 2025</span>';
  const seg = ['simple', 'expert'].map((m) => `<button type="button" data-act="ui" data-ui="${m}" aria-pressed="${S.ui === m}">${m === 'simple' ? 'Simple' : 'Expert'}</button>`).join('');
  return `${left}<div class="seg" role="group" aria-label="Level of detail">${seg}</div>`;
}

function renderPanel() {
  if (!S.meta) return;
  if (!flashTimer) updateHint();
  $('panel-head').innerHTML = headHtml();
  if (S.screen === 'loading') return renderLoading();
  if (S.screen === 'verdict') return renderVerdict();
  return renderPick();
}

// ---------------------------------------------------------------- panel: pick screen
function areaHtml() {
  const c = pdCounts();
  if (!c.total) return '<div id="sec-area"></div>';
  const done = c.ok + c.error, loading = c.pending > 0;
  const ramp = rampFor();
  const info = S.meta.variables[ramp.var] || { name: ramp.var };
  const counts = loading
    ? `Reading the climate… <span class="num">${done} of ${c.total}</span> cells`
    : `${plural(c.land, 'land cell')}${c.sea ? ` · ${c.sea} sea, left out` : ''}${c.error ? ` · ${c.error} failed` : ''}`;
  const climate = S.climate ? `<p class="t-body"><strong>${esc(S.climate.label)}</strong>: ${esc(S.climate.reason)}.</p>` : '';
  const legend = ramp.n > 1 && !loading ? `<div class="stack tight no-print">
      <div class="ramp" style="background:linear-gradient(90deg, rgb(${ramp.lo.join(',')}), rgb(${ramp.hi.join(',')}))"></div>
      <div class="ends"><span>${esc(valueText(ramp.var, ramp.min))}</span><span>dot colour: average ${esc(info.name.toLowerCase())}</span><span>${esc(valueText(ramp.var, ramp.max))}</span></div></div>` : '';
  const allSea = !loading && !c.land && c.sea ? '<p class="note">These cells are all sea. Move the loop over land.</p>' : '';
  return `<div id="sec-area" class="stack">
    <p class="t-cap" aria-live="polite">${counts}</p>
    ${loading ? `<div class="progress"><i style="width:${Math.round(100 * done / c.total)}%"></i></div>` : ''}
    ${climate}${legend}${allSea}
    ${S.note ? `<p class="t-cap">${esc(S.note)}</p>` : ''}
    ${S.capped ? `<p class="t-cap">Large area: cells are sampled evenly so at most ${S.meta.max_points} are fetched.</p>` : ''}
  </div>`;
}

function yearOptions(selected, from, to) {
  let html = '';
  for (let y = from; y <= to; y++) html += `<option value="${y}" ${y === selected ? 'selected' : ''}>${y}</option>`;
  return html;
}

function renderPick() {
  const n = S.picked.size;
  const [y0, y1] = S.years, [first, last] = S.meta.years;
  if (!n) {
    const demo = ['Tunis', 'Riyadh', 'Manitoba'].map((name) => `<button type="button" class="link" data-act="demo" data-name="${name}">${name}</button>`).join(' · ');
    $('panel-body').innerHTML = `<div class="screen">
      <div class="stack">
        <h1 class="t-display">Is the climate changing where you live?</h1>
        <p class="t-body">Check the evidence yourself. Trend Detective tests 45 years of NASA data for the place you choose and tells you, in plain words, whether a change is real.</p>
      </div>
      <ol class="stack t-body" style="counter-reset:s">
        <li><strong>1.</strong> Find a place: move the map or use the search box.</li>
        <li><strong>2.</strong> Draw a loop around it with the pen tool (or hold Shift and drag).</li>
        <li><strong>3.</strong> Choose a question and press Investigate.</li>
      </ol>
      <p class="t-body">Or start with an example: ${demo}</p>
      <button type="button" class="btn demo-btn" data-act="rundemo">${ic('spin')} Watch the demo</button>
      ${S.error ? `<p role="alert" class="note">${esc(S.error)}</p>` : ''}
    </div>`;
    $('panel-foot').innerHTML = `<button class="btn wide" type="button" disabled>Investigate ${ic('next')}</button>`;
    return;
  }
  const rows = S.questions.map((q) => {
    const sel = !S.variable && S.question === q.id;
    return `<button type="button" class="q" data-act="q" data-q="${esc(q.id)}" aria-pressed="${sel}">
      <span class="dot"></span><b>${esc(q.label)}</b><small>${esc(q.vars)}</small>${scanStatus(q.primary)}</button>`;
  }).join('');
  const options = Object.entries(S.meta.variables).map(([id, v]) => `<option value="${esc(id)}" ${S.variable === id ? 'selected' : ''}>${esc(v.name)}</option>`).join('');
  $('panel-body').innerHTML = `<div class="screen">
    <div class="stack">
      <h1 class="t-lead">What do you want to check here?</h1>
      ${areaHtml()}
    </div>
    <div class="stack">
      <div class="qlist">${rows || '<div class="stack" style="padding:14px 0"><span class="skel w80"></span><span class="skel w60"></span></div>'}</div>
      <div class="field"><label for="var">Or one variable</label>
        <select id="var" class="sel grow" data-change="var"><option value="">Choose…</option>${options}</select></div>
      <div class="field"><label for="y0">Years</label>
        <select id="y0" class="sel" data-change="y0" aria-label="First year">${yearOptions(y0, first, last - S.meta.min_years + 1)}</select>
        <span class="t-cap">to</span>
        <select id="y1" class="sel" data-change="y1" aria-label="Last year">${yearOptions(y1, first + S.meta.min_years - 1, last)}</select>
        <span class="t-cap num">${y1 - y0 + 1} years</span></div>
    </div>
    ${S.error ? `<p role="alert" class="note">${esc(S.error)}</p>` : ''}
  </div>`;
  $('panel-foot').innerHTML = `<button id="go" class="btn wide" type="button" data-act="go">Investigate ${ic('next')}</button>`;
  syncGo();
}

function syncGo() {
  const go = $('go');
  if (!go) return;
  const c = pdCounts();
  const ready = S.picked.size > 0 && chosenVars().primary && S.years[1] - S.years[0] + 1 >= S.meta.min_years && !(c.sea && !c.land && !c.pending);
  go.disabled = !ready;
}

// ---------------------------------------------------------------- investigate
async function investigate() {
  const { primary, linked, why } = chosenVars();
  if (!primary) return;
  S.screen = 'loading'; S.error = null; S.cross = null; S.explain = null; S.seasons = null; S.groups = null; S.mapGroups = false;
  zonesLayer.clearLayers();
  renderPanel(); renderPoints();
  try {
    S.result = await api('/api/analyze', { points: [...S.picked.values()], var_id: primary, linked, why, years: S.years });
    S.screen = 'verdict'; S.tab = 'series'; S.view = 'anomaly';
    drawZones();
    loadCrossCheck();
    loadSeasons();
  } catch (err) {
    S.screen = 'pick'; S.error = err.message;
  }
  renderPanel(); renderPoints(); updateHash();
}

// The second dataset can take a minute, so the verdict shows first and this part fills in after.
async function loadCrossCheck() {
  const R = S.result;
  if (!R.has_second_source) { S.cross = { status: 'none' }; return loadExplain(R); }
  S.cross = { status: 'loading' };
  try {
    const data = await api('/api/crosscheck', { points: [...S.picked.values()], var_id: R.var_id, years: R.years });
    if (S.result === R) S.cross = { status: 'ok', data };
  } catch (err) {
    if (S.result === R) S.cross = { status: 'error', error: err.message };
  }
  if (S.screen === 'verdict' && S.result === R) { patch('sec-cross', crossHtml()); drawCharts(); }
  loadExplain(R);
}

async function loadExplain(R) {
  if (S.result !== R) return;
  S.explain = { status: 'loading' };
  const cross = S.cross && S.cross.status === 'ok' ? S.cross.data : null;
  try {
    const data = await api('/api/explain', {
      points: [...S.picked.values()], var_id: R.var_id, years: R.years, question_id: S.variable ? null : S.question,
      cross: cross && { state: cross.state, headline: cross.headline, detail: cross.detail },
    });
    if (S.result === R) S.explain = { status: 'ok', data };
  } catch (err) {
    if (S.result === R) S.explain = { status: 'error', error: err.message };
  }
  if (S.screen === 'verdict' && S.result === R) patch('sec-explain', explainHtml());
}

async function loadSeasons() {
  const R = S.result;
  S.seasons = { status: 'loading' };
  try {
    const data = await api('/api/seasons', { points: [...S.picked.values()], var_id: R.var_id, years: R.years });
    if (S.result === R) S.seasons = { status: 'ok', data };
  } catch (err) {
    if (S.result === R) S.seasons = { status: 'error', error: err.message };
  }
  if (S.screen === 'verdict' && S.result === R) patch('sec-seasons', seasonsHtml());
}

async function loadGroups() {
  const R = S.result;
  S.groups = { status: 'loading' };
  try {
    const data = await api('/api/clusters', { points: [...S.picked.values()], years: R.years });
    if (S.result === R) S.groups = { status: 'ok', data };
  } catch (err) {
    if (S.result === R) S.groups = { status: 'error', error: err.message };
  }
  if (S.screen === 'verdict' && S.result === R && S.tab === 'groups') { patch('sec-tab', tabHtml()); drawCharts(); syncGroupsOnMap(); updateHint(); }
}

function backToPick() {
  S.screen = 'pick'; S.result = null; S.cross = null; S.explain = null; S.seasons = null; S.groups = null; S.mapGroups = false;
  zonesLayer.clearLayers(); highlightCell(null);
  if (lasso) lasso.addTo(map);
  renderPanel(); renderPoints(); updateHash();
  setTimeout(afterPointData, 0);
}

function newCase() {
  pushHistory();
  S.picked.clear(); S.added.clear(); S.note = null; S.capped = false; S.variable = null; S.userChose = false; S.place = null;
  S.question = S.questions[0] ? S.questions[0].id : null;
  setLasso(null);
  backToPick();
  $('tool-undo').disabled = !S.history.length;
  setMode('pan');
}

// ---------------------------------------------------------------- verdict: sections
function explainHtml() {
  const E = S.explain;
  if (E && E.status === 'error') return '<section id="sec-explain"></section>';
  if (!E || E.status === 'loading') {
    return `<section id="sec-explain" class="stack" aria-live="polite"><h2 class="t-title">In plain words</h2>
      <span class="skel"></span><span class="skel w80"></span><span class="skel w60"></span></section>`;
  }
  const D = E.data;
  const by = D.source === 'gemini'
    ? 'Written by an AI model (Google Gemini) from the numbers this app computed, and checked to contain no others.'
    : 'Written by the app from its own results.';
  const next = (D.next || []).slice(0, 3).map((q) => `<li><button type="button" class="link" data-act="next" data-q="${esc(q.id)}">${esc(q.label)}${ic('next', 's')}</button></li>`).join('');
  return `<section id="sec-explain" class="stack" aria-live="polite">
    <h2 class="t-title">In plain words</h2>
    <p class="t-body" style="color:var(--ink)">${esc(D.summary)}</p>
    <p class="t-cap">${by}</p>
    ${next ? `<div class="stack tight no-print" style="padding-top:4px"><h3 class="t-cap" style="font-weight:600;color:var(--char)">Investigate next, same area</h3><ul class="stack tight">${next}</ul></div>` : ''}
  </section>`;
}

function decadesHtml() {
  const R = S.result, D = R.decades || [], v = R.variable, d = v.decimals ?? 2;
  if (D.length < 2) return '';
  const vals = D.map((x) => x.mean || 0);
  const top = Math.max(0, ...vals), bottom = Math.min(0, ...vals), span = (top - bottom) || 1;
  const zero = (top / span) * 100;
  const bars = D.map((x, i) => {
    const up = (x.mean || 0) >= 0, h = (Math.abs(x.mean || 0) / span) * 100;
    const y = up ? zero - h : zero;
    const label = `${x.decade}: ${fmt(x.mean, d)} ${v.units || ''} (${x.first_year} to ${x.last_year}, ${x.months} months)`;
    return `<button type="button" class="bar ${up ? 'up' : 'down'}" style="--i:${i};--origin:${up ? 'bottom' : 'top'}" data-hover="decade" data-y0="${x.first_year}" data-y1="${x.last_year}" aria-label="${esc(label)}" title="${esc(label)}">
      <span class="plot"><span style="position:absolute;inset:18px 0">
        <span class="zero" style="top:${zero}%"></span>
        <span class="fill" style="top:${y}%;height:${Math.max(h, 0.8)}%"></span>
        <span class="val" style="${up ? `bottom:calc(${100 - y}% + 3px)` : `top:calc(${y + h}% + 3px)`}">${fmt(x.mean, d)}</span>
      </span></span>
      <span class="lab">${esc(x.decade)}</span></button>`;
  }).join('');
  return `<section class="stack">
    <div class="stack tight"><h2 class="t-title">Decade by decade</h2>
      <p class="t-cap">Average ${term('anomaly', 'difference from usual')} in each decade, in ${esc(v.units || 'units')}. Zero is the ${R.years[0]} to ${R.years[1]} average.</p></div>
    <div class="bars" role="group" aria-label="Average anomaly per decade">${bars}</div>
  </section>`;
}

function untilHtml() {
  const r = S.result.res, yts = r.years_to_significance;
  if (r.tier === 'significant' || yts === null || yts === undefined || yts > 50) return '';
  const span = r.span_years, year = Math.round(S.result.years[1] + yts);
  return `<section class="stack tight">
    <p class="t-body">Not settled yet: if this rate continued, about <strong class="num">${Math.round(yts)} more years</strong> of data would be needed to be sure, around ${year}.</p>
    <div class="until" role="img" aria-label="${Math.round(span)} years of data so far, about ${Math.round(yts)} more needed"><i style="width:${Math.round(100 * span / (span + yts))}%"></i></div>
    <div class="ends"><span>${S.result.years[0]}</span><span>${S.result.years[1]} · today</span><span>about ${year}</span></div>
  </section>`;
}

function accessReason(text) {
  return /BadAuthentication|credential|Earthdata Login/i.test(text || '') ? 'the NASA Earthdata login in .env is missing or was refused' : (text || 'no answer from Giovanni');
}

function crossHtml() {
  const R = S.result, C = S.cross, expert = S.ui === 'expert';
  const open = (inner, cls = '') => `<section id="sec-cross" class="stack ${cls}" aria-live="polite">${inner}</section>`;
  const quiet = (text) => (expert ? open(`<p class="t-cap">${esc(text)}</p>`) : open(''));
  if (!R.has_second_source || (C && C.status === 'none')) return quiet(`No independent NASA dataset for ${R.variable.name.toLowerCase()} yet.`);
  if (!C || C.status === 'loading') {
    return open(`<p class="t-cap">${ic('spin', 's spin')} Checking a second NASA dataset…</p><span class="skel w80"></span>`);
  }
  if (C.status === 'error') return quiet(`Second dataset not checked: ${C.error}`);
  const D = C.data;
  if (D.state === 'none') return quiet(`No independent NASA dataset for ${R.variable.name.toLowerCase()} yet.`);
  if (!D.sources || !D.sources.length) return quiet(`Second dataset not checked: ${accessReason(D.detail)}.`);
  const look = D.look || D.state, v = R.variable, d = v.decimals ?? 2, u = v.units || '';
  const head = look === 'agree' ? `<span class="status" style="color:var(--teal-d)">${ic('check')}${D.state === 'agree' ? 'A second NASA dataset agrees' : esc(D.headline)}</span>`
    : look === 'disagree' ? `<span class="status" style="color:var(--amber)">${ic('info')}${esc(D.headline)}</span>`
      : `<span class="status flat">${ic('layers')}${esc(D.headline)}</span>`;
  const rows = D.sources.map((s) => `<dt>${esc(s.label)}</dt><dd>${fmt(s.slope_decade, d)} ${esc(u)}<small> per decade · ${esc(statusOf(s.tier, s.slope_decade).words.toLowerCase())}${expert && s.ci_decade ? `<br>95% range ${fmt(s.ci_decade[0], d)} to ${fmt(s.ci_decade[1], d)}` : ''}</small></dd>`).join('');
  return open(`${head}
    <details class="more" ${expert ? 'open' : ''}><summary>${ic('chev', 's')}How do we know?</summary><div class="inside">
      <p class="t-body">${esc(D.detail)}</p>
      <dl class="kv">${rows}</dl>
      ${expert && D.r !== null && D.r !== undefined ? `<p class="t-cap num">Year-to-year agreement between the two: r = ${fmt(D.r, 2)} over ${D.years[0]} to ${D.years[1]}.</p>` : ''}
      ${expert && D.figure ? '<div id="cross-chart" data-chart="cross"></div>' : ''}
      ${D.note ? `<p class="t-cap">${esc(D.note)}</p>` : ''}
    </div></details>`);
}

function elevationHtml() {
  const E = S.result.elevation;
  if (!E || !E.applies) return '';
  const v = S.result.variable, d = v.decimals ?? 2, u = v.units || '';
  const row = (name, g) => `<dt>${name}: ${plural(g.points, 'cell')}, about ${g.mean_elevation_m} m</dt><dd>${fmt(g.slope_decade, d)} ${esc(u)}<small> per decade · ${esc(statusOf(g.tier, g.slope_decade).words.toLowerCase())}</small></dd>`;
  return `<section class="stack tight">
    <span class="status flat">${ic('hill')}Uplands and lowlands</span>
    <p class="t-body">${esc(E.sentence)}</p>
    ${S.ui === 'expert' ? `<dl class="kv">${row('Higher', E.high)}${row('Lower', E.low)}</dl>
      <p class="t-cap">Cells range from ${E.range_m[0]} m to ${E.range_m[1]} m, split at ${E.cut_m} m (NASA POWER cell elevation).</p>` : ''}
  </section>`;
}

function seasonsHtml() {
  const Z = S.seasons, open = (inner) => `<section id="sec-seasons" class="stack">${inner}</section>`;
  if (!Z || Z.status === 'error') return open('');
  const title = '<h2 class="t-title">Season by season</h2>';
  if (Z.status === 'loading') return open(`${title}<span class="skel"></span><span class="skel w80"></span>`);
  const rows = Z.data.seasons.filter((s) => s.slope_decade !== null);
  if (rows.length < 2) return open('');
  const v = S.result.variable, d = v.decimals ?? 2;
  const m = Math.max(...rows.map((s) => Math.abs(s.slope_decade))) || 1;
  const body = rows.map((s) => {
    const w = (Math.abs(s.slope_decade) / m) * 48, up = s.slope_decade >= 0;
    const word = { significant: 'clear', suggestive: 'possible', none: 'unclear' }[s.tier];
    return `<span>${esc(s.label)}</span>
      <span class="track"><i class="${up ? 'up' : 'down'} ${s.tier === 'none' ? 'unclear' : ''}" style="${up ? `left:50%` : `left:${50 - w}%`};width:${w}%"></i><b style="left:50%"></b></span>
      <span class="v">${fmt(s.slope_decade, d)} <small>${word}</small></span>`;
  }).join('');
  return open(`<div class="stack tight">${title}<p class="t-body">${esc(Z.data.sentence)}</p></div>
    <div class="seasons" role="group" aria-label="Trend per decade in each season, in ${esc(v.units || 'units')}">${body}</div>
    <p class="t-cap">Rate per decade in ${esc(v.units || 'units')}, same tests on each season's months. Faded bars are marked unclear: no clear trend in that season.</p>`);
}

function testsHtml() {
  const R = S.result, r = R.res, v = R.variable, d = v.decimals ?? 2, u = v.units || '';
  const [lo, hi] = r.ci_decade;
  const m = Math.max(Math.abs(lo), Math.abs(hi), Math.abs(r.slope_decade)) * 1.25 || 1;
  const pos = (x) => ((x + m) / (2 * m)) * 100;
  const up = r.slope_decade >= 0 ? 'up' : 'down';
  const res = (p) => (p < 0.05 ? '<span class="pass">passes</span>' : p < 0.10 ? '<span class="weak">borderline</span>' : '<span class="fail">not passed</span>');
  return `<section class="stack">
    <h2 class="t-title">The tests</h2>
    <table class="tests"><thead><tr><th>Test</th><th class="n">p-value</th><th class="n">At 5%</th></tr></thead><tbody>
      <tr><td>Straight-line fit<small>OLS on monthly anomalies, Newey-West errors (12-month lag)</small></td><td class="n">${fmtP(r.p_ttest)}</td><td class="n">${res(r.p_ttest)}</td></tr>
      <tr><td>Rank test<small>Mann-Kendall, Hamed-Rao correction for autocorrelation</small></td><td class="n">${fmtP(r.p_mk)}</td><td class="n">${res(r.p_mk)}</td></tr>
    </tbody></table>
    <div class="stack tight">
      <div class="row between" style="font-size:13.5px"><span>${term('range', '95% range')} of the rate</span><strong class="num">${fmt(lo, d)} to ${fmt(hi, d)} ${esc(u)} per decade</strong></div>
      <div class="range"><span class="band ${up}" style="left:${pos(lo)}%;width:${pos(hi) - pos(lo)}%"></span><span class="zero" style="left:calc(${pos(0)}% - 1px)"></span><span class="est ${up}" style="left:calc(${pos(r.slope_decade)}% - 2px)"></span></div>
      <div class="ends"><span>${fmt(-m, d)}</span><span>0</span><span>${fmt(m, d)}</span></div>
    </div>
    <dl class="kv">
      <dt>Rate (straight-line fit)</dt><dd>${fmt(r.slope_decade, d)} ${esc(u)}<small> per decade</small></dd>
      <dt>Sen's slope (robust rate)</dt><dd>${fmt(r.sen_decade, d)} ${esc(u)}<small> per decade</small></dd>
      ${r.pct_decade !== null && r.pct_decade !== undefined ? `<dt>Share of the average</dt><dd>${fmt(r.pct_decade, 1)}%<small> per decade</small></dd>` : ''}
      <dt>Record</dt><dd>${esc(r.start)} to ${esc(r.end)}<small> · ${r.n_months} months, ${r.missing_months} missing</small></dd>
      <dt>Cells averaged</dt><dd>${R.points_used} land<small> of ${R.points.length} picked</small></dd>
      ${r.tier !== 'significant' && r.years_to_significance !== null && r.years_to_significance <= 50 ? `<dt>More data needed at this rate</dt><dd>about ${Math.round(r.years_to_significance)} years</dd>` : ''}
    </dl>
  </section>`;
}

function groupsBody() {
  const Gp = S.groups;
  if (!Gp || Gp.status === 'loading') return '<div class="stack" role="status"><p class="t-cap">Testing every cell on three variables and grouping the ones that change alike…</p><span class="skel"></span><span class="skel w60"></span></div>';
  if (Gp.status === 'error') return `<p class="t-body">${esc(Gp.error)}</p>`;
  const D = Gp.data;
  if (!D.ok) return `<p class="t-body">${esc(D.reason)}</p>`;
  const names = D.features.map((f) => f.name.toLowerCase());
  const list = D.zones.map((z) => `<li><span class="swatch" style="background:${z.color}"></span>
      <span><strong>Group ${esc(z.zone)}</strong> · ${esc(z.where)} · ${plural(z.points, 'cell')}<br>${esc(z.summary)}</span></li>`).join('');
  const views = [['2d', 'Flat'], ['3d', '3D']].map(([id, label]) => `<button type="button" data-act="gview" data-gview="${id}" aria-pressed="${S.groupView === id}">${label}</button>`).join('');
  return `<div class="stack">
    <p class="t-body">Each cell was tested on its own for ${esc(names[0])}, ${esc(names[1])} and ${esc(names[2])}. Cells whose trends look alike share a colour, here and on the map.</p>
    <ul class="stack group-list">${list}</ul>
    <div class="seg" role="group" aria-label="Plot view" style="align-self:flex-start">${views}</div>
    <div id="groups-chart" data-chart="groups"></div>
    <p class="t-cap">${S.groupView === '3d' ? `Drag to turn the cube. Up: ${esc(D.features[2].name.toLowerCase())}.` : `Right = warming faster; up = ${esc(names[1])} rising. Hover a dot to find its cell on the map.`} Groups describe the data; they are not a test. Each cell's significance is in the Zones tab.</p>
  </div>`;
}

function tabHtml() {
  const R = S.result, r = R.res, v = R.variable;
  let body = '';
  if (S.tab === 'series') {
    const seg = [['anomaly', 'Anomalies'], ['raw', 'Raw values']].map(([id, label]) => `<button type="button" data-act="view" data-view="${id}" aria-pressed="${S.view === id}">${label}</button>`).join('');
    body = `<div class="stack"><div class="seg" role="group" aria-label="Series" style="align-self:flex-start">${seg}</div>
      <div id="chart" data-chart="series"></div>
      <p class="t-cap">Monthly ${S.view === 'anomaly' ? term('anomaly', 'anomalies') + ' with the fitted trend and its 95% range' : 'values with their 12-month average'}. Hover a decade bar above to mark its years here.</p></div>`;
  } else if (S.tab === 'zones') {
    const z = R.zones;
    body = z && z.length ? `<div class="stack">
        <p class="t-body">Each square on the map is one cell, tested on its own. A dot means its trend survives the ${term('fdr', 'correction for testing ' + z.length + ' cells at once')} (Benjamini-Hochberg, 10%). Hover a square for its rate, p-values and q-value.</p>
        <dl class="kv"><dt>Clear rise</dt><dd>${plural(z.filter((x) => x.significant && x.slope_decade > 0).length, 'cell')}</dd>
          <dt>Clear fall</dt><dd>${plural(z.filter((x) => x.significant && x.slope_decade < 0).length, 'cell')}</dd>
          <dt>No clear trend</dt><dd>${plural(z.filter((x) => !x.significant).length, 'cell')}</dd></dl></div>`
      : '<p class="t-body">Pick at least two land cells to compare them.</p>';
  } else if (S.tab === 'groups') {
    body = groupsBody();
  } else if (S.tab === 'evidence') {
    const L_ = R.link;
    body = `<div class="stack"><p class="t-body"><strong>${esc(v.name)}.</strong> ${esc(v.definition || '')}</p>
      ${v.source ? `<p class="t-cap">Source: ${esc(v.source)}</p>` : ''}${v.caveat ? `<p class="t-cap">Caveat: ${esc(v.caveat)}</p>` : ''}
      ${L_ ? `<hr class="rule"><p class="t-body"><strong>Checked against ${esc(L_.name.toLowerCase())}.</strong> ${esc(L_.why)} ${L_.r === null ? 'Not enough overlapping months to compare.' : `Month-to-month anomalies move together with r = <span class="num">${fmt(L_.r, 2)}</span> (${L_.n} months). A link like this is consistent with a connection; it is not proof of cause.`}</p>` : ''}</div>`;
  } else {
    body = `<div class="stack"><ol class="method">
      <li>NASA POWER monthly values at each picked cell; sea cells left out, land cells averaged by cos(latitude).</li>
      <li>Anomalies: each month minus its usual value, so the seasons do not look like trends.</li>
      <li>Rate per decade from a straight-line fit with Newey-West errors (t-test, 95% range).</li>
      <li>Mann-Kendall (Hamed-Rao) and Sen's slope as a second, rank-based test.</li>
      <li>Significant only when both tests give p &lt; 0.05 and agree on direction; possible when either gives p &lt; 0.10.</li>
      <li>Per-cell maps correct for testing many cells at once (Benjamini-Hochberg, 10%).</li>
    </ol>
    <p class="t-cap">Climate is usually judged over 30 years or more (World Meteorological Organization); ${r.start.slice(0, 4)} to ${r.end.slice(0, 4)} gives ${Math.round(r.span_years)}. A trend in one variable shows a change here; it does not by itself prove climate change or name a cause.</p>
    <a class="link" href="/docs/validation.md" target="_blank" rel="noopener">How we checked the method (validation notes)${ic('next', 's')}</a></div>`;
  }
  return `<div id="sec-tab" data-tabpanel role="tabpanel">${body}</div>`;
}

function questionTitle() {
  const q = !S.variable && S.questions.find((x) => x.id === S.question);
  return q && q.primary === S.result.var_id ? q.label : `What is happening to ${S.result.variable.name.toLowerCase()}?`;
}

function renderVerdict() {
  const R = S.result, r = R.res, v = R.variable, d = v.decimals ?? 2, u = v.units || '';
  const st = statusOf(r.tier, r.slope_decade);
  const total = r.total_change;
  const change = r.tier !== 'none' && total !== null && total !== undefined
    ? `About <strong class="num">${fmt(total, d)} ${esc(u)}</strong> over the ${Math.round(r.span_years)} years since ${R.years[0]}${r.pct_decade !== null && r.pct_decade !== undefined ? ` (${fmt(r.pct_decade, 1)}% of the average ${term('decade', 'per decade')})` : ''}.`
    : esc(R.words.detail.replace(/\s*This shows a change, not its cause\.?/, ''));
  const expert = S.ui === 'expert';
  const tabs = [['series', 'Time series'], ['zones', 'Zones'], ['groups', 'Groups'], ['evidence', 'Evidence'], ['method', 'Method']].map(([id, label]) =>
    `<button type="button" role="tab" class="tab" data-act="tab" data-tab="${id}" aria-selected="${S.tab === id}">${label}</button>`).join('');
  const today = new Date().toISOString().slice(0, 10);

  $('panel-body').innerHTML = `<div class="screen">
    <div class="print-only"><strong>Trend Detective case report</strong> · ${today} · ${plural(R.points_used, 'NASA POWER land cell')} · ${R.years[0]} to ${R.years[1]}</div>
    <div class="stack">
      <p class="t-q">${esc(questionTitle())}</p>
      <h1 class="t-display">${esc(R.words.headline)}</h1>
      <span class="status big ${st.cls}">${ic(st.icon)}${st.words}</span>
      <p class="t-body">${change}</p>
      <p class="t-cap">This shows a change, not its cause. ${plural(R.points_used, 'land cell')}, ${R.years[0]} to ${R.years[1]}.</p>
    </div>
    ${decadesHtml()}
    ${untilHtml()}
    <div class="aside stack" style="gap:16px">${explainHtml()}</div>
    ${crossHtml()}
    ${seasonsHtml()}
    ${elevationHtml()}
    ${expert ? `<hr class="rule no-print">${testsHtml()}
      <div class="stack no-print"><div class="tabs" role="tablist" aria-label="Details">${tabs}</div>${tabHtml()}</div>`
    : `<button type="button" class="link no-print" data-act="ui" data-ui="expert">See the tests, the maps and the method${ic('next', 's')}</button>`}
    <p class="print-only t-cap">Data: NASA POWER (MERRA-2 reanalysis) monthly values${S.cross && S.cross.status === 'ok' && S.cross.data.sources ? ', cross-checked with a second NASA dataset via Giovanni' : ''}. Method: monthly anomalies; straight-line fit with Newey-West errors and Mann-Kendall test. This shows a change, not its cause. SI-assisted: parts of this app were drafted with Claude (Anthropic) and reviewed by the team.</p>
  </div>`;

  const menu = expert ? `<details class="menu"><summary class="btn quiet">${ic('save', 's')}Download</summary><div class="items">
      <button type="button" data-act="csv">Series (CSV)</button>
      <button type="button" data-act="cells">Per-cell trends (CSV)</button>
      <button type="button" data-act="json">This case (JSON)</button>
      <button type="button" data-act="print">Printable report</button></div></details>`
    : `<button type="button" class="btn quiet" data-act="print">${ic('print', 's')}Report</button>`;
  $('panel-foot').innerHTML = `<div class="row">${menu}
      <button type="button" class="btn quiet" data-act="share">${ic('link', 's')}Copy link</button>
      <span style="flex:1"></span>
      <button type="button" class="btn dark" data-act="new">New case</button></div>
    <p class="t-cap" style="margin-top:8px;font-size:11.5px">SI-assisted: parts of this app were drafted with Claude (Anthropic) and reviewed by the team.</p>`;
  drawCharts();
  syncGroupsOnMap();
}

// Plotly charts are drawn into whichever chart holders are on screen and not drawn yet.
function drawCharts() {
  const R = S.result;
  if (!R) return;
  document.querySelectorAll('[data-chart]:not([data-drawn])').forEach((el) => {
    el.dataset.drawn = '1';
    const kind = el.dataset.chart;
    if (kind === 'series') {
      const fig = R.figures[S.view];
      Plotly.react(el, fig.data, { ...fig.layout, autosize: true }, { displayModeBar: false, responsive: true });
    } else if (kind === 'cross' && S.cross && S.cross.status === 'ok' && S.cross.data.figure) {
      const cf = S.cross.data.figure;
      Plotly.react(el, cf.data, { ...cf.layout, autosize: true }, { displayModeBar: false, responsive: true });
    } else if (kind === 'groups' && S.groups && S.groups.status === 'ok' && S.groups.data.ok) {
      const gf = S.groups.data[S.groupView === '3d' ? 'figure3d' : 'figure2d'];
      Plotly.react(el, gf.data, { ...gf.layout, autosize: true }, { displayModeBar: S.groupView === '3d', displaylogo: false, responsive: true });
      el.on('plotly_hover', (ev) => highlightCell(ev.points[0].customdata));
      el.on('plotly_unhover', () => highlightCell(null));
    }
  });
}

// Hovering a decade bar marks its years on the monthly series (Expert, Time series tab).
function markYears(y0, y1) {
  const el = $('chart');
  if (!el || !el.dataset.drawn || !window.Plotly) return;
  const shapes = y0 ? [{ type: 'rect', xref: 'x', yref: 'paper', x0: `${y0}-01-01`, x1: `${y1}-12-31`, y0: 0, y1: 1, fillcolor: 'rgba(4,100,96,0.12)', line: { width: 0 } }] : [];
  try { Plotly.relayout(el, { shapes }); } catch (_) { /* chart is being redrawn */ }
}

// ---------------------------------------------------------------- map layers for the verdict
function drawZones() {
  zonesLayer.clearLayers();
  const z = S.result && S.result.zones;
  if (!z || !z.length) return;
  if (lasso) lasso.remove();
  const v = S.result.variable, d = Math.max(v.decimals ?? 2, 2);
  const vmax = Math.max(...z.map((r) => Math.abs(r.slope_decade || 0))) || 1;
  for (const r of z) {
    const t = (r.slope_decade || 0) / vmax;
    const col = t >= 0 ? mix([244, 243, 239], [194, 65, 12], t) : mix([244, 243, 239], [29, 78, 216], -t);
    const rect = L.rectangle([[r.lat - DLAT / 2, r.lon - DLON / 2], [r.lat + DLAT / 2, r.lon + DLON / 2]],
      { color: '#FFFFFF', weight: 1, fillColor: col, fillOpacity: 0.85 });
    rect.bindTooltip(`<strong>${r.lat.toFixed(2)}°, ${r.lon.toFixed(2)}°</strong><br>${fmt(r.slope_decade, d)} ${esc(v.units || '')} per decade · ${(r.slope_decade || 0) >= 0 ? 'rising' : 'falling'}<br>`
      + `p = ${fmtP(r.p_ttest)} (fit), ${fmtP(r.p_mk)} (rank) · q = ${fmtP(r.q_fdr)}<br>${r.significant ? 'Clear trend after the many-cells correction' : 'No clear trend at this cell'}`);
    rect.on('mouseover', () => highlightCell([r.lat, r.lon])).on('mouseout', () => highlightCell(null));
    rect.addTo(zonesLayer);
    if (r.significant) L.circleMarker([r.lat, r.lon], { radius: 3.5, color: '#1F2024', fillColor: '#1F2024', fillOpacity: 1, interactive: false }).addTo(zonesLayer);
  }
}

function syncGroupsOnMap() {
  const want = S.screen === 'verdict' && S.ui === 'expert' && S.tab === 'groups' && S.groups && S.groups.status === 'ok' && S.groups.data.ok;
  if (want && !S.mapGroups) {
    zonesLayer.clearLayers();
    const ps = S.groups.data.points;
    for (const p of ps) {
      L.rectangle([[p.lat - DLAT / 2, p.lon - DLON / 2], [p.lat + DLAT / 2, p.lon + DLON / 2]], { color: '#FFFFFF', weight: 1, fillColor: p.color, fillOpacity: 0.8 })
        .bindTooltip(`Group ${p.zone} · ${p.lat.toFixed(2)}°, ${p.lon.toFixed(2)}°`).addTo(zonesLayer);
    }
    map.fitBounds([[Math.min(...ps.map((p) => p.lat)) - DLAT, Math.min(...ps.map((p) => p.lon)) - DLON],
      [Math.max(...ps.map((p) => p.lat)) + DLAT, Math.max(...ps.map((p) => p.lon)) + DLON]], { ...mapPadding(), maxZoom: 9 });
    S.mapGroups = true;
  } else if (!want && S.mapGroups) {
    S.mapGroups = false;
    drawZones();
  }
}

let highlight = null;
function highlightCell(ll) {
  if (highlight) { highlight.remove(); highlight = null; }
  if (!ll) return;
  highlight = L.rectangle([[ll[0] - DLAT / 2, ll[1] - DLON / 2], [ll[0] + DLAT / 2, ll[1] + DLON / 2]],
    { color: '#1F2024', weight: 3, fill: false, interactive: false }).addTo(map);
}

// ---------------------------------------------------------------- loading screen
function renderLoading() {
  const n = S.picked.size;
  $('panel-body').innerHTML = `<div class="screen" role="status" aria-live="polite">
    <div class="stack"><p class="t-q">Asking NASA POWER for ${plural(n, 'cell')} and running the tests…</p>
      <span class="skel" style="height:26px;width:90%"></span><span class="skel" style="height:26px;width:55%"></span><span class="skel w40"></span></div>
    <div class="stack"><span class="skel"></span><span class="skel w80"></span><span class="skel w60"></span></div>
    <p class="t-cap">New cells take a few seconds each. Cells fetched before come from the cache.</p></div>`;
  $('panel-foot').innerHTML = `<button class="btn wide" type="button" disabled>${ic('spin', 'spin')}Investigating…</button>`;
}

// ---------------------------------------------------------------- downloads, sharing, printing
function download(name, text, type) {
  const a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob([text], { type }));
  a.download = name;
  a.click();
  URL.revokeObjectURL(a.href);
}

function downloadSeries() {
  const R = S.result;
  download(`trend_detective_${R.var_id}_${R.years[0]}_${R.years[1]}.csv`,
    [`month,${R.var_id}`].concat(R.series.month.map((m, i) => `${m},${R.series.value[i] ?? ''}`)).join('\n'), 'text/csv');
}

function downloadCells() {
  const R = S.result, cols = ['lat', 'lon', 'slope_decade', 'pct_decade', 'p_ttest', 'p_mk', 'q_fdr', 'significant'];
  if (!R.zones || !R.zones.length) return flash('Per-cell trends need at least two land cells.');
  download(`trend_detective_${R.var_id}_cells.csv`, [cols.join(',')].concat(R.zones.map((z) => cols.map((c) => z[c] ?? '').join(','))).join('\n'), 'text/csv');
}

function downloadCase() {
  const R = S.result, { figures, ...rest } = R;   // figures are drawings of the same numbers
  const strip = (o) => { if (!o) return null; const { figure, ...x } = o; return x; };
  download(`trend_detective_${R.var_id}_case.json`, JSON.stringify({
    app: 'Trend Detective', generated: new Date().toISOString(), link: location.href,
    request: { points: [...S.picked.values()], var_id: R.var_id, years: R.years },
    result: rest, cross_check: S.cross && S.cross.status === 'ok' ? strip(S.cross.data) : null,
    seasons: S.seasons && S.seasons.status === 'ok' ? S.seasons.data : null,
  }, null, 1), 'application/json');
}

// The case lives in the URL hash, so a link reopens it: cells, years, question, level of detail, screen.
function updateHash() {
  const parts = [];
  if (S.picked.size) parts.push('p=' + [...S.picked.values()].map(([lat, lon]) => `${+lat.toFixed(4)},${+lon.toFixed(4)}`).join(';'));
  if (S.years[0] !== S.meta.years[0] || S.years[1] !== S.meta.years[1]) parts.push(`y=${S.years[0]}-${S.years[1]}`);
  const { primary } = chosenVars();
  if (S.picked.size && primary) { parts.push('v=' + primary); if (!S.variable && S.question) parts.push('q=' + S.question); }
  if (S.ui === 'expert') parts.push('m=expert');
  if (S.screen === 'verdict') parts.push('s=v');
  ownHash = parts.length ? '#' + parts.join('&') : '';
  try { history.replaceState(null, '', ownHash || location.pathname); } catch (_) { /* sandboxed frame */ }
}
// A link pasted into a tab that already shows the app only changes the hash: reopen that case.
let ownHash = location.hash;
window.addEventListener('hashchange', () => { if (location.hash !== ownHash) location.reload(); });

function restoreFromHash() {
  const h = new URLSearchParams(location.hash.replace(/^#/, ''));
  if (h.get('m') === 'expert' || h.get('m') === 'simple') S.ui = h.get('m');
  const cells = (h.get('p') || '').split(';').map((s) => s.split(',').map(Number))
    .filter((c) => c.length === 2 && c.every(Number.isFinite) && Math.abs(c[0]) <= 90 && Math.abs(c[1]) <= 180)
    .slice(0, S.meta.max_points).map(([lat, lon]) => snap(lat, lon));
  if (!cells.length) return false;
  const y = (h.get('y') || '').split('-').map(Number);
  if (y.length === 2 && y[0] >= S.meta.years[0] && y[1] <= S.meta.years[1] && y[1] - y[0] + 1 >= S.meta.min_years) S.years = y;
  S.picked = new Map(cells.map(([lat, lon]) => [keyOf(lat, lon), [lat, lon]]));
  S.widened = true;
  if (h.get('v') && S.meta.variables[h.get('v')]) { S.variable = h.get('v'); S.userChose = true; S.restoreQ = h.get('q'); }
  map.fitBounds(L.latLngBounds(cells).pad(0.6), { ...mapPadding(), maxZoom: 8, animate: false });
  return h.get('s') === 'v' && !!S.variable;
}

function share() {
  updateHash();
  const done = () => flash('Link copied: it reopens this case');
  if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(location.href).then(done, () => flash('Copy the link from the address bar'));
  else flash('Copy the link from the address bar');
}

window.addEventListener('beforeprint', () => document.querySelectorAll('#panel details.more').forEach((el) => { el.open = true; }));

// ---------------------------------------------------------------- place search (bundled list, no third party)
const norm = (s) => s.normalize('NFD').replace(/[̀-ͯ]/g, '').replace(/[’']/g, '').toLowerCase();
const search = { items: [], active: -1 };

function searchRender() {
  const input = $('place'), box = $('place-results');
  const q = norm(input.value.trim());
  const all = window.TD_PLACES || [];
  const hits = q ? all.filter((p) => norm(p[0]).startsWith(q)).concat(all.filter((p) => !norm(p[0]).startsWith(q) && (norm(p[0]).includes(q) || norm(p[1]).split(/[ ·]+/).some((w) => w.startsWith(q))))) : all.slice(0, 8);
  search.items = hits.slice(0, 8);
  if (search.active >= search.items.length) search.active = search.items.length - 1;
  box.innerHTML = search.items.length
    ? search.items.map((p, i) => `<button type="button" class="result" role="option" id="place-${i}" data-i="${i}" aria-selected="${i === search.active}"><span>${esc(p[0])}</span><small>${esc(p[1])}</small></button>`).join('')
    : '<p class="none">No match in the built-in list. Move the map there instead.</p>';
  box.hidden = false;
  input.setAttribute('aria-expanded', 'true');
  if (search.active >= 0) input.setAttribute('aria-activedescendant', `place-${search.active}`); else input.removeAttribute('aria-activedescendant');
}

function searchClose() { $('place-results').hidden = true; $('place').setAttribute('aria-expanded', 'false'); search.active = -1; }

function goToPlace(p, investigateNow) {
  S.place = { name: p[0], lat: p[2], lon: p[3] }; S.placeFresh = true;
  $('place').value = p[0];
  searchClose();
  if (S.screen !== 'pick') backToPick();
  if (investigateNow) return selectAround(S.place);
  const target = L.latLng(p[2], p[3]);
  const shift = phone() ? [0, window.innerHeight * 0.2] : [220, 0];      // keep the place clear of the panel
  const centre = map.unproject(map.project(target, 7).add(shift), 7);
  if (reduceMotion || document.hidden) map.setView(centre, 7, { animate: false }); else map.flyTo(centre, 7, { duration: 1.1 });
  updateHint();
}

$('place').addEventListener('input', () => { search.active = -1; searchRender(); });
$('place').addEventListener('focus', searchRender);
$('place').addEventListener('keydown', (e) => {
  if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
    e.preventDefault();
    const n = search.items.length;
    if (n) { search.active = (search.active + (e.key === 'ArrowDown' ? 1 : -1) + n) % n; searchRender(); }
  } else if (e.key === 'Enter') {
    const p = search.items[Math.max(search.active, 0)];
    if (p) goToPlace(p);
  } else if (e.key === 'Escape') { searchClose(); e.target.blur(); }
});
$('place-results').addEventListener('click', (e) => { const b = e.target.closest('[data-i]'); if (b) goToPlace(search.items[+b.dataset.i]); });
document.addEventListener('pointerdown', (e) => { if (!e.target.closest('.search')) searchClose(); });
$('hint-action').addEventListener('click', () => { if (S.place) selectAround(S.place); });

// ---------------------------------------------------------------- first-run welcome: watch demo or explore
function showWelcome() {
  const el = $('coach');
  el.hidden = false;
  el.innerHTML = `
    <div class="welcome-logo" aria-hidden="true">
      <svg><use href="#logo"/></svg>
    </div>
    <h2 class="t-title" style="margin-top:4px">Trend Detective</h2>
    <p class="t-body" style="color:var(--char)">45 years of NASA data. Pick any area on Earth. Find out if the climate is changing there.</p>
    <div class="row stack tight" style="gap:8px;margin-top:4px">
      <button type="button" class="btn wide" data-welcome="demo">Watch the demo</button>
      <button type="button" class="link" style="text-align:center" data-welcome="skip">Explore yourself</button>
    </div>`;
}
$('coach').addEventListener('click', (e) => {
  const b = e.target.closest('[data-welcome]');
  if (!b) return;
  $('coach').hidden = true;
  pref.set('coach', 'done');
  if (b.dataset.welcome === 'demo') runDemo();
});

// ---------------------------------------------------------------- events (one delegated listener per kind)
const ACTIONS = {
  ui: (b) => { S.ui = b.dataset.ui; pref.set('ui', S.ui); renderPanel(); updateHash(); if (S.screen === 'verdict') updateHint(); },
  back: () => backToPick(),
  new: () => newCase(),
  go: () => investigate(),
  q: (b) => { S.question = b.dataset.q; S.variable = null; S.userChose = true; renderPanel(); updateHash(); },
  next: (b) => { S.question = b.dataset.q; S.variable = null; S.userChose = true; investigate(); },
  demo: (b) => { const p = (window.TD_PLACES || []).find((x) => x[0] === b.dataset.name); if (p) goToPlace(p, true); },
  tab: (b) => { S.tab = b.dataset.tab; if (S.tab === 'groups' && !S.groups) loadGroups(); renderPanel(); },
  view: (b) => { S.view = b.dataset.view; patch('sec-tab', tabHtml()); drawCharts(); },
  gview: (b) => { S.groupView = b.dataset.gview; patch('sec-tab', tabHtml()); drawCharts(); },
  csv: () => downloadSeries(), cells: () => downloadCells(), json: () => downloadCase(),
  print: () => window.print(),
  share: () => share(),
};
$('panel').addEventListener('click', (e) => {
  const b = e.target.closest('[data-act]');
  if (!b || b.disabled) return;
  const menu = b.closest('details.menu');
  if (menu) menu.open = false;
  ACTIONS[b.dataset.act](b);
});
$('panel').addEventListener('change', (e) => {
  const kind = e.target.dataset.change, [first, last] = S.meta.years, min = S.meta.min_years;
  if (kind === 'var') { S.variable = e.target.value || null; S.userChose = !!S.variable; if (!S.variable) adoptQuestion(); }
  else if (kind === 'y0') { S.years[0] = +e.target.value; if (S.years[1] - S.years[0] + 1 < min) S.years[1] = Math.min(last, S.years[0] + min - 1); }
  else if (kind === 'y1') { S.years[1] = +e.target.value; if (S.years[1] - S.years[0] + 1 < min) S.years[0] = Math.max(first, S.years[1] - min + 1); }
  else return;
  renderPanel(); renderPoints(); updateHash();
  setTimeout(maybeScan, 0);
});
const hoverDecade = (e, on) => { const b = e.target.closest && e.target.closest('[data-hover="decade"]'); if (b) markYears(on ? b.dataset.y0 : null, b.dataset.y1); };
$('panel').addEventListener('mouseover', (e) => hoverDecade(e, true));
$('panel').addEventListener('mouseout', (e) => hoverDecade(e, false));
$('panel').addEventListener('focusin', (e) => hoverDecade(e, true));
$('panel').addEventListener('focusout', (e) => hoverDecade(e, false));

$('tool-pan').addEventListener('click', () => setMode('pan'));
$('tool-draw').addEventListener('click', () => setMode(S.mode === 'draw' ? 'pan' : 'draw'));
$('tool-points').addEventListener('click', () => setMode(S.mode === 'points' ? 'pan' : 'points'));
$('tool-undo').addEventListener('click', undo);
$('tool-clear').addEventListener('click', () => {
  if (S.screen !== 'pick' || !S.picked.size) return;
  pushHistory();
  S.picked.clear(); S.added.clear(); S.note = null; S.capped = false;
  setLasso(null);
  selectionChanged();
});
map.on('moveend', () => { if (S.mode === 'points') renderPoints(); });
document.addEventListener('keydown', (e) => {
  const typing = /^(INPUT|SELECT|TEXTAREA)$/.test(e.target.tagName);
  if ((e.ctrlKey || e.metaKey) && !e.shiftKey && e.key.toLowerCase() === 'z' && !typing) { e.preventDefault(); undo(); }
  if (e.key === 'Escape' && S.mode === 'draw') { window.cancelLasso(); setMode('pan'); }
});

// ---------------------------------------------------------------- demo walkthrough: auto-playing guided cases

let demoRunning = false, demoAbort = null;

function demoWait(ms) {
  return new Promise((resolve, reject) => {
    const id = setTimeout(resolve, ms);
    demoAbort = () => { clearTimeout(id); reject(new Error('stopped')); };
  });
}

function demoPoll(fn, interval, timeout) {
  return new Promise((resolve, reject) => {
    const end = Date.now() + timeout;
    let id;
    const check = () => {
      if (fn()) { resolve(); return; }
      if (Date.now() > end) { resolve(); return; }
      id = setTimeout(check, interval);
    };
    demoAbort = () => { clearTimeout(id); reject(new Error('stopped')); };
    check();
  });
}

function demoOverlay(step, total, caption) {
  let el = $('demo-bar');
  if (!el) {
    el = document.createElement('div');
    el.id = 'demo-bar';
    document.body.appendChild(el);
  }
  const pips = Array.from({ length: total }, (_, i) =>
    `<i class="demo-pip${i < step ? ' done' : ''}${i === step ? ' on' : ''}"></i>`).join('');
  el.innerHTML = `<div class="demo-inner">
    <span class="demo-pips">${pips}</span>
    <span class="demo-cap">${esc(caption)}</span>
    <button id="demo-stop" type="button" class="demo-stop">Stop demo</button>
  </div>`;
  el.hidden = false;
  $('demo-stop').addEventListener('click', () => { if (demoAbort) demoAbort(); });
}

function demoHide() {
  const el = $('demo-bar');
  if (el) el.hidden = true;
}

async function runDemo() {
  if (demoRunning) return;
  demoRunning = true;
  pref.set('coach', 'done');
  $('coach').hidden = true;
  try {
    if (S.screen === 'verdict') newCase();
    demoOverlay(0, 1, 'Finding your location…');
    const here = await new Promise((resolve) => {
      if (!navigator.geolocation) return resolve(null);
      navigator.geolocation.getCurrentPosition((p) => resolve([p.coords.latitude, p.coords.longitude]), () => resolve(null), { timeout: 6000, maximumAge: 600000 });
    });
    const c0 = map.getCenter(), [lat, lon] = here || [c0.lat, c0.lng];
    demoOverlay(0, 1, here ? 'Selecting the area around you…' : 'Selecting the area in the middle of the map…');
    S.place = { name: 'this area', lat, lon };
    selectAround(S.place);
    await demoPoll(() => S.climate !== null, 300, 15000);
    const qLabel = (S.questions.find((q) => q.id === S.question) || {}).label || 'climate trend here';
    demoOverlay(0, 1, qLabel);
    await demoWait(600);
    investigate();
    await demoPoll(() => S.screen === 'verdict' && S.result, 300, 30000);
    await demoPoll(() => S.explain && S.explain.status !== 'loading', 400, 20000);
    renderPanel();
    demoOverlay(0, 1, `${qLabel} — now try your own area!`);
    await demoWait(10000);
  } catch (_) { /* stopped */ }
  demoHide();
  demoRunning = false;
  demoAbort = null;
}

ACTIONS.rundemo = () => runDemo();

// ---------------------------------------------------------------- boot
(async function boot() {
  S.ui = pref.get('ui', 'simple') === 'expert' ? 'expert' : 'simple';
  try {
    S.meta = await api('/api/meta');
    S.years = [...S.meta.years];
  } catch (err) {
    $('panel-body').innerHTML = `<p role="alert" class="note">Could not reach the server: ${esc(err.message)}</p>`;
    return;
  }
  // Land outline for "nearest land cells"; without it the app falls back to NASA's own land/sea answer per cell.
  fetch('/land.json').then((r) => r.json()).then((d) => { S.isLand = G.landTester(d.polygons); }).catch(() => { /* optional */ });
  const reopenVerdict = restoreFromHash();
  setMode('pan');
  if (S.picked.size) selectionChanged(); else { renderPanel(); loadQuestions(); }
  if (reopenVerdict) investigate();
  else if (!S.picked.size && pref.get('coach', '') !== 'done') showWelcome();
})();
