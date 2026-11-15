// SI-assisted: parts of this file were drafted with Claude (Anthropic) and reviewed by the team
// Node checks for web/static/grid.js (run by tests/test_grid_js.py). Prints "ok N" or throws.
'use strict';
const assert = require('assert');
const path = require('path');
const fs = require('fs');
const G = require(path.join(__dirname, '..', 'web', 'static', 'grid.js'));
const land = G.landTester(JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'web', 'static', 'land.json'), 'utf8')).polygons);
let n = 0;
const check = (name, fn) => { fn(); n++; };

check('snap matches td/fetch.py cells', () => {
  assert.deepStrictEqual(G.snap(36.6, 10.1), [36.5, 10]);
  assert.deepStrictEqual(G.snap(36.74, 9.6), [36.5, 9.375]);
  assert.deepStrictEqual(G.snap(36.75, 9.6), [37, 9.375]);       // half rounds up, like the server
});

check('land mask: known land and sea', () => {
  assert.ok(land(36.5, 10.0), 'Tunis is land');
  assert.ok(land(24.5, 46.875), 'Riyadh is land');
  assert.ok(!land(35.0, 18.75), 'central Mediterranean is sea');
  assert.ok(!land(0, -30), 'mid Atlantic is sea');
});

check('tiny loop on land: itself first, then nearest neighbours', () => {
  const cells = G.nearestLandCells(36.52, 10.02, 4, land);
  assert.strictEqual(cells.length, 4);
  assert.deepStrictEqual(cells[0], [36.5, 10]);
  const d = cells.map((c) => G.haversineKm(36.52, 10.02, c[0], c[1]));
  assert.deepStrictEqual(d, [...d].sort((a, b) => a - b), 'ordered by true distance');
  assert.ok(d[3] < 90, 'all within the first ring');
});

check('sea-only loop: skips sea, returns nearby land only', () => {
  const cells = G.nearestLandCells(37.6, 10.9, 4, land);          // just off Cap Bon
  assert.strictEqual(cells.length, 4);
  for (const c of cells) assert.ok(land(c[0], c[1]));
  assert.ok(Math.max(...cells.map((c) => G.haversineKm(37.6, 10.9, c[0], c[1]))) < 220);
});

check('open ocean: gives up after the maximum radius', () => {
  assert.deepStrictEqual(G.nearestLandCells(0, -30, 4, land, 3), []);
});

check('coastal loop: land cells only, never a sea cell', () => {
  const cells = G.nearestLandCells(35.2, 11.3, 6, land);          // Gulf of Hammamet shore
  assert.strictEqual(cells.length, 6);
  for (const c of cells) assert.ok(land(c[0], c[1]));
});

check('antimeridian: neighbours wrap from +179 to -180', () => {
  const all = () => true;
  const cells = G.nearestLandCells(-17.0, 179.9, 9, all, 1);      // near Fiji, every cell accepted
  const lons = cells.map((c) => c[1]);
  assert.ok(lons.includes(-180) && lons.includes(179.375) && lons.includes(-179.375), JSON.stringify(lons));
  assert.ok(lons.every((x) => x >= -180 && x < 180));
  assert.ok(Math.max(...cells.map((c) => G.haversineKm(-17.0, 179.9, c[0], c[1]))) < 120, 'wrapped cells are near, not across the world');
  assert.strictEqual(new Set(cells.map((c) => G.keyOf(c[0], c[1]))).size, 9);
});

check('poles: no rows beyond 90 degrees', () => {
  const cells = G.nearestLandCells(89.9, 0, 20, () => true, 2);
  assert.ok(cells.every((c) => Math.abs(c[0]) <= 90));
});

check('ties break north first', () => {
  const cells = G.nearestLandCells(10.0, 10.0, 3, (lat, lon) => lon === 10, 1);   // only the column through the centre
  assert.deepStrictEqual(cells, [[10, 10], [10.5, 10], [9.5, 10]]);
});

console.log('ok ' + n);
