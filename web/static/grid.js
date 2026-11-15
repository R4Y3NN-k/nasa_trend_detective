// SI-assisted: parts of this file were drafted with Claude (Anthropic) and reviewed by the team
// MERRA-2 grid maths for the map UI. Owner: C (dashboard). Plain functions, no DOM: also run by tests under Node.
(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else root.TDGrid = factory();
})(typeof self !== 'undefined' ? self : this, function () {
  'use strict';

  const DLAT = 0.5, DLON = 0.625;           // same cells as td/fetch.py
  const NLON = Math.round(360 / DLON);      // 576 columns around the world
  const ILAT_MAX = Math.round(90 / DLAT);   // rows -180..180

  const cellLat = (i) => +(i * DLAT).toFixed(4);
  const cellLon = (j) => +(-180 + (((j % NLON) + NLON) % NLON) * DLON).toFixed(4);   // wraps at the antimeridian
  const rowOf = (lat) => Math.floor(lat / DLAT + 0.5);
  const colOf = (lon) => Math.floor((lon + 180) / DLON + 0.5);
  const snap = (lat, lon) => [cellLat(Math.max(-ILAT_MAX, Math.min(ILAT_MAX, rowOf(lat)))), cellLon(colOf(lon))];
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

  // Even-odd point in polygon. ring = [[x, y], ...]; here x = longitude, y = latitude.
  function inRing(x, y, ring) {
    let hit = false;
    for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
      const xi = ring[i][0], yi = ring[i][1], xj = ring[j][0], yj = ring[j][1];
      if ((yi > y) !== (yj > y) && x < (xj - xi) * (y - yi) / (yj - yi) + xi) hit = !hit;
    }
    return hit;
  }

  // Land test from a list of {b: [w, s, e, n], r: ring} polygons (Natural Earth 110 m, see land.json).
  function landTester(polygons) {
    return (lat, lon) => {
      for (const p of polygons) {
        if (lon < p.b[0] || lon > p.b[2] || lat < p.b[1] || lat > p.b[3]) continue;
        if (inRing(lon, lat, p.r)) return true;
      }
      return false;
    };
  }

  function haversineKm(lat1, lon1, lat2, lon2) {
    const R = 6371, rad = Math.PI / 180;
    const dLat = (lat2 - lat1) * rad, dLon = (lon2 - lon1) * rad;
    const a = Math.sin(dLat / 2) ** 2 + Math.cos(lat1 * rad) * Math.cos(lat2 * rad) * Math.sin(dLon / 2) ** 2;
    return 2 * R * Math.asin(Math.min(1, Math.sqrt(a)));
  }

  // The k nearest land cells to (lat, lon): breadth-first rings on the grid (8 neighbours, growing Chebyshev
  // distance), each ring sorted by true distance (ties: north first, then west). Exact on a regular lattice,
  // so no approximate index is needed. Stops at k cells or after maxRing rings. Returns [[lat, lon], ...].
  function nearestLandCells(lat, lon, k, isLand, maxRing = 3) {
    const i0 = Math.max(-ILAT_MAX, Math.min(ILAT_MAX, rowOf(lat))), j0 = colOf(lon);
    const found = [], seen = new Set();
    for (let ring = 0; ring <= maxRing && found.length < k; ring++) {
      const cells = [];
      for (let di = -ring; di <= ring; di++) {
        for (let dj = -ring; dj <= ring; dj++) {
          if (Math.max(Math.abs(di), Math.abs(dj)) !== ring) continue;      // only the ring's edge
          const i = i0 + di;
          if (i < -ILAT_MAX || i > ILAT_MAX) continue;                      // no rows beyond the poles
          const c = [cellLat(i), cellLon(j0 + dj)];
          const key = keyOf(c[0], c[1]);
          if (seen.has(key)) continue;
          seen.add(key);
          if (isLand(c[0], c[1])) cells.push({ c, d: haversineKm(lat, lon, c[0], c[1]) });
        }
      }
      cells.sort((a, b) => a.d - b.d || b.c[0] - a.c[0] || a.c[1] - b.c[1]);
      for (const x of cells) if (found.length < k) found.push(x.c);
    }
    return found;
  }

  return { DLAT, DLON, NLON, snap, keyOf, cellsIn, inRing, landTester, haversineKm, nearestLandCells };
});
