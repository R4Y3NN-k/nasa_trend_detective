# SI-assisted: parts of this file were drafted with Claude (Anthropic) and reviewed by the team
"""Nearest land cells on the MERRA-2 grid, for loops that are smaller than a cell or fall on the sea.

The cells sit on a regular lattice (0.5 deg lat x 0.625 deg lon), so neighbours come from integer grid
indices: a ring (breadth-first) search around the centre cell, each ring sorted by true distance.
No approximate index is needed.

Contract:
    ring(lat, lon, r) -> [(lat, lon), ...]            # cells at Chebyshev distance r, nearest first
    nearest_land(center, k, land_many, have=(), max_rings=3) -> ([(lat, lon), ...], rings_searched)
        # land_many(cells) -> the subset of cells that is land; called once per ring
"""
from __future__ import annotations

import math

DLAT, DLON = 0.5, 0.625
N_LON = 576                      # 360 / 0.625
MAX_I = 180                      # 90 / 0.5


def _index(lat: float, lon: float) -> tuple[int, int]:
    i = max(-MAX_I, min(MAX_I, math.floor(lat / DLAT + 0.5)))
    j = math.floor((lon + 180) / DLON + 0.5) % N_LON
    return i, j


def _cell(i: int, j: int) -> tuple[float, float]:
    return round(i * DLAT, 4), round(-180 + (j % N_LON) * DLON, 4)


def haversine_km(a, b) -> float:
    (la1, lo1), (la2, lo2) = a, b
    p1, p2 = math.radians(la1), math.radians(la2)
    h = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lo2 - lo1) / 2) ** 2
    return 2 * 6371.0 * math.asin(min(1.0, math.sqrt(h)))


def ring(lat: float, lon: float, r: int) -> list[tuple[float, float]]:
    """Cells exactly r steps away (8-neighbour lattice), nearest first, ties north first. Wraps at +-180."""
    i0, j0 = _index(lat, lon)
    cells = set()
    for di in range(-r, r + 1):
        for dj in range(-r, r + 1):
            if max(abs(di), abs(dj)) != r or abs(i0 + di) > MAX_I:
                continue
            cells.add(_cell(i0 + di, j0 + dj))
    return sorted(cells, key=lambda c: (round(haversine_km((lat, lon), c), 3), -c[0], c[1]))


def nearest_land(center, k: int, land_many, have=(), max_rings: int = 3):
    """Up to k land cells around `center`, counting the land cells already in `have`; only the new ones return."""
    lat, lon = center
    known = {(round(a, 4), round(b, 4)) for a, b in have}
    found: list[tuple[float, float]] = []
    r = 0
    for r in range(max_rings + 1):
        if len(known) + len(found) >= k:
            return found, max(r - 1, 0)
        candidates = [c for c in ring(lat, lon, r) if c not in known]
        land = set(land_many(candidates)) if candidates else set()
        for c in candidates:                      # already nearest first
            if c in land and len(known) + len(found) < k:
                found.append(c)
    return found, r
