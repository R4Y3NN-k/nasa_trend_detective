# SI-assisted: parts of this file were drafted with Claude (Anthropic) and reviewed by the team
"""MODIS NDVI from finished AppEEARS area jobs. Owner: A (data). Step 8 (optional).

D submits the area jobs (task IDs in docs/appeears_tasks.md); this module downloads a finished
task's statistics CSV and turns it into a monthly NDVI series (0-1). Results are cached, so each task
is downloaded once. Needs EARTHDATA_USERNAME / EARTHDATA_PASSWORD (environment or .env).

AppEEARS API: https://appeears.earthdatacloud.nasa.gov/api/
    POST /login (basic auth) -> token;  GET /task/{id} -> status;  GET /bundle/{id} -> files;
    GET /bundle/{id}/{file_id} -> file

Contract:
    load_ndvi(task_id) -> pd.Series      # monthly mean NDVI, 0-1, index month start
"""
from __future__ import annotations

import io
import os

import pandas as pd
import requests

from td import cache
from td.fetch import FetchError
from td.giovanni import _load_env_file

API = "https://appeears.earthdatacloud.nasa.gov/api"
TIMEOUT_S = 120


class AppeearsError(FetchError):
    """AppEEARS is not ready or not reachable. The message is safe to show users."""


def _token() -> str:
    _load_env_file()
    user, pwd = os.environ.get("EARTHDATA_USERNAME"), os.environ.get("EARTHDATA_PASSWORD")
    if not (user and pwd):
        raise AppeearsError("AppEEARS needs an Earthdata Login: set EARTHDATA_USERNAME and EARTHDATA_PASSWORD in .env.")
    r = requests.post(f"{API}/login", auth=(user, pwd), timeout=TIMEOUT_S)
    if r.status_code != 200:
        raise AppeearsError(f"AppEEARS login failed (HTTP {r.status_code}).")
    return r.json()["token"]


def _get(path: str, token: str) -> requests.Response:
    r = requests.get(f"{API}/{path}", headers={"Authorization": f"Bearer {token}"}, timeout=TIMEOUT_S,
                     allow_redirects=True)
    if r.status_code != 200:
        raise AppeearsError(f"AppEEARS answered HTTP {r.status_code} for {path.split('/')[0]}.")
    return r


def _pick_csv(files: list) -> dict:
    """The area statistics CSV of the NDVI product (fallback: any results CSV)."""
    csvs = [f for f in files if f.get("file_name", "").lower().endswith(".csv")]
    stats = [f for f in csvs if "statistics" in f["file_name"].lower()]
    pick = stats or [f for f in csvs if "results" in f["file_name"].lower()]
    if not pick:
        raise AppeearsError("This AppEEARS task has no statistics CSV (was it an area request with CSV output?).")
    return pick[0]


def parse_ndvi_csv(text: str) -> pd.Series:
    """AppEEARS CSV -> monthly mean NDVI (0-1).

    Area statistics: rows per date and layer ("Dataset" like "_250m_16_days_NDVI", column "Mean").
    Point results: one "..._NDVI" column per row; points are averaged per date.
    16-day composites are averaged into calendar months.
    """
    df = pd.read_csv(io.StringIO(text))
    if {"Dataset", "Date", "Mean"} <= set(df.columns):
        df = df[df["Dataset"].astype(str).str.contains("NDVI", case=False)]
        values, dates = pd.to_numeric(df["Mean"], errors="coerce"), df["Date"]
    else:
        col = next((c for c in df.columns if c.upper().endswith("_NDVI")), None)
        if col is None or "Date" not in df.columns:
            raise AppeearsError("No NDVI column in the AppEEARS CSV.")
        values, dates = pd.to_numeric(df[col], errors="coerce"), df["Date"]
    s = pd.Series(values.to_numpy(), index=pd.to_datetime(dates, errors="coerce")).dropna()
    if s.empty:
        raise AppeearsError("The AppEEARS CSV holds no NDVI values.")
    if s.abs().max() > 1.5:                   # unscaled integers (scale factor 0.0001)
        s = s * 0.0001
    s = s[(s >= -0.2) & (s <= 1.0)]
    monthly = s.groupby(s.index.to_period("M").to_timestamp()).mean()
    monthly.index.name = "month"
    return monthly.sort_index()


def load_ndvi(task_id: str) -> pd.Series:
    """Monthly NDVI (0-1) from a finished AppEEARS area task; cached after the first download."""
    key = cache.make_key("appeears-ndvi", task_id)
    hit = cache.get(key)
    if hit is None:
        token = _token()
        status = _get(f"task/{task_id}", token).json().get("status", "unknown")
        if status != "done":
            raise AppeearsError(f"AppEEARS task {task_id} is '{status}', not done yet. Try again later.")
        f = _pick_csv(_get(f"bundle/{task_id}", token).json().get("files", []))
        series = parse_ndvi_csv(_get(f"bundle/{task_id}/{f['file_id']}", token).text)
        hit = {"task_id": task_id, "file": f["file_name"],
               "values": {d.strftime("%Y-%m"): float(v) for d, v in series.items()}}
        cache.put(key, hit)
    s = pd.Series(hit["values"], dtype="float64")
    s.index = pd.to_datetime(s.index, format="%Y-%m")
    s.index.name, s.name = "month", "NDVI"
    s.attrs.update(units="NDVI (0-1)", source=f"MODIS NDVI via AppEEARS ({hit['file']})")
    return s.sort_index()
