# SI-assisted: parts of this file were drafted with Claude (Anthropic) and reviewed by the team
"""NASA POWER client: grid of points, land mask, cos(latitude)-weighted average. Owner: A (data).

1. grid_points(): split the box into equal cells, starting at MIN_SPACING_DEG (0.5 deg) and widening
   x1.25 until there are at most MAX_POINTS (30) cells; take each cell centre and snap it to the nearest
   MERRA-2 grid cell (0.5 deg lat x 0.625 deg lon), so no two points sample the same reanalysis cell.
2. One POWER monthly point request per point (T2M, PRECTOTCORR, GWETTOP), 4 at a time, cached.
3. Land mask on GWETTOP: sea when it is all missing or fixed at 1.0 (POWER reports saturated
   topsoil, 1.0 every month, over open water).
4. Average the land points month by month with cos(latitude) weights.

API: https://power.larc.nasa.gov/docs/services/api/

Contract:
    fetch_box(box, start_year, end_year) -> BoxData     # box = (west, south, east, north)
    grid_points(box) -> list[tuple[float, float]]       # (lat, lon)
"""
from __future__ import annotations

import math
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

import numpy as np
import pandas as pd
import requests

from td import cache
from td.config import MAX_POINTS, MIN_SPACING_DEG

POWER_URL = "https://power.larc.nasa.gov/api/temporal/monthly/point"
CORE_PARAMS = ("T2M", "PRECTOTCORR", "GWETTOP")   # what fetch_box() returns (Streamlit app)
# Extra variables let the map UI ask the questions that fit each climate (snow and frost in Canada, extreme heat
# in Arabia). Same request, same cache entry per point: POWER returns them all in one call.
POWER_PARAMS = CORE_PARAMS + ("T2M_MAX", "T2M_MIN", "FROST_DAYS", "PRECSNOLAND", "SNODP", "RH2M")
FILL_VALUE = -999.0
TIMEOUT_S = 90
RETRIES = 3
WORKERS = 4
MERRA2_DLAT, MERRA2_DLON = 0.5, 0.625


@dataclass
class BoxData:
    data: pd.DataFrame        # index: month start (DatetimeIndex); columns: variable ids ("T2M", ...)
    points_total: int         # grid points requested
    points_used: int          # land points averaged
    points: list              # [(lat, lon, is_land)]
    point_data: dict          # {(lat, lon): DataFrame like .data}, land points only


class FetchError(RuntimeError):
    """Raised when a box cannot be fetched. The message is safe to show users."""


# ------------------------------------------------------------------ grid

def _check_box(box) -> tuple[float, float, float, float]:
    try:
        west, south, east, north = (float(v) for v in box)
    except (TypeError, ValueError):
        raise FetchError("The region must be four numbers: west, south, east, north.") from None
    if not (-180 <= west < east <= 180 and -90 <= south < north <= 90):
        raise FetchError("The region box is not valid: west must be less than east and south less than north.")
    return west, south, east, north


def _snap(lat: float, lon: float) -> tuple[float, float]:
    """Nearest MERRA-2 cell centre."""
    slat = math.floor(lat / MERRA2_DLAT + 0.5) * MERRA2_DLAT             # round half up, not half-even
    slon = -180 + math.floor((lon + 180) / MERRA2_DLON + 0.5) * MERRA2_DLON
    return round(min(max(slat, -90.0), 90.0), 4), round(min(max(slon, -180.0), 179.375), 4)


def grid_points(box) -> list[tuple[float, float]]:
    """Cell centres covering the box, at most MAX_POINTS, snapped to MERRA-2 cells; (lat, lon) pairs."""
    west, south, east, north = _check_box(box)
    width, height = east - west, north - south
    spacing = MIN_SPACING_DEG
    while True:
        nx, ny = max(1, math.floor(width / spacing)), max(1, math.floor(height / spacing))
        if nx * ny <= MAX_POINTS:
            break
        spacing *= 1.25
    pts = []
    for j in range(ny):
        for i in range(nx):
            p = _snap(south + (j + 0.5) * height / ny, west + (i + 0.5) * width / nx)
            if p not in pts:
                pts.append(p)
    return pts


# ------------------------------------------------------------------ one point

def _request_power(lat: float, lon: float, start_year: int, end_year: int) -> dict:
    """GET one point from POWER: timeout 90 s, 3 retries, longer back-off on HTTP 429."""
    params = {"parameters": ",".join(POWER_PARAMS), "community": "AG", "latitude": lat, "longitude": lon,
              "start": start_year, "end": end_year, "format": "JSON"}
    last = "no answer"
    for attempt in range(RETRIES + 1):
        try:
            r = requests.get(POWER_URL, params=params, timeout=TIMEOUT_S)
        except requests.RequestException as err:
            last = type(err).__name__
        else:
            if r.status_code == 200:
                try:
                    return r.json()
                except ValueError:
                    last = "a reply that was not JSON"
            elif r.status_code == 429 or r.status_code >= 500:
                last = f"HTTP {r.status_code}"
            else:
                raise FetchError(f"NASA POWER refused the request for ({lat}, {lon}): HTTP {r.status_code}.")
        if attempt < RETRIES:
            time.sleep((10 if last == "HTTP 429" else 2) * (attempt + 1))
    raise FetchError(f"NASA POWER did not answer for ({lat}, {lon}) after {RETRIES + 1} tries ({last}).")


def parse_power(js: dict) -> pd.DataFrame:
    """properties.parameter.<NAME>.<YYYYMM> -> monthly DataFrame; month 13 (annual) dropped, -999 -> NaN."""
    try:
        raw = js["properties"]["parameter"]
    except (KeyError, TypeError):
        raise FetchError("NASA POWER sent an answer without data.") from None
    cols = {}
    for name in POWER_PARAMS:
        vals = {pd.Timestamp(year=int(k[:4]), month=int(k[4:6]), day=1): v
                for k, v in raw.get(name, {}).items() if not k.endswith("13")}
        cols[name] = pd.Series(vals, dtype="float64")
    df = pd.DataFrame(cols).sort_index()
    df[df <= FILL_VALUE + 0.5] = np.nan
    df.index.name = "month"
    coords = (js.get("geometry") or {}).get("coordinates") or []
    elev = coords[2] if len(coords) > 2 else None
    df.attrs["elevation_m"] = float(elev) if elev is not None and elev > FILL_VALUE + 0.5 else None
    return df


def fetch_point(lat: float, lon: float, start_year: int, end_year: int) -> pd.DataFrame:
    """Monthly data for one point; the raw POWER answer is cached, so each point is fetched once.

    df.attrs["elevation_m"] holds the MERRA-2 cell's mean elevation in metres (None if POWER sent none).
    """
    key = cache.make_key("power-monthly-point", lat, lon, start_year, end_year, POWER_PARAMS)
    js = cache.get(key)
    if js is None:
        js = _request_power(lat, lon, start_year, end_year)
        cache.put(key, js)
    return parse_power(js)


def _keep_attrs(new: pd.DataFrame, old: pd.DataFrame) -> pd.DataFrame:
    new.attrs.update(old.attrs)
    return new


def elevations(point_data: dict) -> dict:
    """{(lat, lon): elevation in metres or None} for BoxData.point_data, e.g. to split mountains from lowlands."""
    return {pt: df.attrs.get("elevation_m") for pt, df in point_data.items()}


def is_land(df: pd.DataFrame) -> bool:
    """Sea when GWETTOP is all missing or saturated (1.0) in every month."""
    g = df["GWETTOP"].dropna() if "GWETTOP" in df else pd.Series(dtype=float)
    return len(g) > 0 and float(g.min()) < 0.999


def area_mean(point_data: dict) -> pd.DataFrame:
    """cos(latitude)-weighted mean of the points, month by month; a missing value drops out of its month."""
    num = den = None
    for (lat, _lon), df in point_data.items():
        w = math.cos(math.radians(lat))
        part, valid = df.fillna(0.0) * w, df.notna() * w
        num = part if num is None else num.add(part, fill_value=0.0)
        den = valid if den is None else den.add(valid, fill_value=0.0)
    out = num / den.where(den > 0)
    out.index.name = "month"
    return out


# ------------------------------------------------------------------ the box

def fetch_box(box, start_year: int, end_year: int, progress=None) -> BoxData:
    """Monthly NASA POWER data for a box, averaged over its land points.

    progress: optional callback(done, total), e.g. for a progress bar.
    """
    if start_year > end_year:
        raise FetchError("The first year must come before the last year.")
    pts = grid_points(box)

    def one(pt):
        try:
            return pt, fetch_point(pt[0], pt[1], start_year, end_year), None
        except FetchError as err:
            return pt, None, err

    frames, errors = {}, []
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        for done, (pt, df, err) in enumerate(pool.map(one, pts), start=1):
            if err is not None:
                errors.append(err)
            else:
                frames[pt] = df
            if progress:
                progress(done, len(pts))
    if errors:
        raise FetchError(f"NASA POWER did not answer for {len(errors)} of {len(pts)} points. Please try again "
                         f"in a minute (the points already downloaded are kept). First error: {errors[0]}")

    land = {pt: df for pt, df in frames.items() if is_land(df)}
    if not land:
        raise FetchError("This box has no land points (it looks like open sea). Move it over land.")
    months = pd.date_range(f"{start_year}-01-01", f"{end_year}-12-01", freq="MS", name="month")
    data = area_mean(land).reindex(months)[list(CORE_PARAMS)]
    return BoxData(
        data=data,
        points_total=len(pts),
        points_used=len(land),
        points=[(lat, lon, (lat, lon) in land) for lat, lon in pts],
        point_data={pt: _keep_attrs(df.reindex(months), df) for pt, df in land.items()},
    )
