# SI-assisted: parts of this file were drafted with Claude (Anthropic) and reviewed by the team
"""Second NASA sources via Giovanni (harmony-py): GPM IMERG rain and AIRS surface air temperature. Owner: A. Step 7.

Follows NASA's GES DISC notebook "How to Access the Giovanni Area-Averaged Time Series ... Using
Python" (nasa/gesdisc-tutorials): a harmony Request with a BBox, average="area", format="text/csv".
Giovanni answers with a CSV: a header block, then "time,mean_<variable>".

Needs an Earthdata Login: EARTHDATA_USERNAME and EARTHDATA_PASSWORD (or EARTHDATA_TOKEN) in the
environment or in .env (gitignored). Every result is cached, so each request costs quota once
(check the monthly quota at https://api.giovanni.earthdata.nasa.gov/quota).
If Giovanni fails twice the call raises GiovanniError (a FetchError), so the app can carry on with a
single source.

Contract:
    fetch_series_giovanni(var_id, box, start_year, end_year) -> pd.Series   # monthly, index month start
"""
from __future__ import annotations

import datetime as dt
import io
import os
import tempfile
from pathlib import Path

import pandas as pd

from td import cache
from td.fetch import FetchError

# var_id -> Giovanni configured variable (https://api.giovanni.earthdata.nasa.gov/configured-variables/)
GIOVANNI_VARIABLES = {
    "IMERG": {
        "variable": "GPM_3IMERGM_07_precipitation",
        "short_name": "GPM_3IMERGM",
        "version": "07",
        "native_units": "mm/hr",
        "to_units": ("mm/day", 24.0),     # match PRECTOTCORR (mm/day)
        "label": "GPM IMERG (satellites + rain gauges)",
    },
    # AIRS on NASA's Aqua satellite (from Sep 2002). Mean of the ~1:30 pm (A) and ~1:30 am (D) passes,
    # close to a daily mean, to compare with T2M (MERRA-2 reanalysis): an independent check on temperature.
    "AIRS_T": {
        "variables": ["AIRS3STM_7_0_SurfAirTemp_A", "AIRS3STM_7_0_SurfAirTemp_D"],
        "short_name": "AIRS3STM",
        "version": "7.0",
        "native_units": "K",
        "to_units": ("°C", 1.0),
        "offset": -273.15,
        "label": "AIRS (Aqua satellite, day and night passes)",
    },
}
ATTEMPTS = 2
ENV_FILE = Path(__file__).resolve().parent.parent / ".env"


class GiovanniError(FetchError):
    """Giovanni failed (twice) or is not configured. The message is safe to show users."""


# ------------------------------------------------------------------ credentials

def _load_env_file(path: Path = ENV_FILE) -> None:
    """Minimal .env reader (KEY=value lines); never overrides variables already set."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _client():
    from harmony import Client

    _load_env_file()
    token = os.environ.get("EARTHDATA_TOKEN")
    user, pwd = os.environ.get("EARTHDATA_USERNAME"), os.environ.get("EARTHDATA_PASSWORD")
    if token:
        return Client(token=token)
    if user and pwd:
        return Client(auth=(user, pwd))
    raise GiovanniError("Giovanni needs an Earthdata Login: set EARTHDATA_USERNAME and EARTHDATA_PASSWORD in .env.")


# ------------------------------------------------------------------ request

def _collection(short_name: str, version: str):
    """(concept_id, first_day, last_day) from NASA's catalog (CMR); no login needed."""
    import earthaccess

    found = earthaccess.search_datasets(short_name=short_name, version=version)
    if not found:
        raise GiovanniError(f"Collection {short_name} v{version} not found in NASA's catalog.")
    c = found[0]
    cid = c.concept_id() if callable(c.concept_id) else c.concept_id
    rng = (c["umm"].get("TemporalExtents") or [{}])[0].get("RangeDateTimes") or [{}]
    first = pd.Timestamp(rng[0].get("BeginningDateTime", "1998-01-01")).tz_localize(None)
    last = pd.Timestamp(rng[-1].get("EndingDateTime") or dt.datetime.now()).tz_localize(None)
    return cid, first, last


def _run_giovanni(spec: dict, box, start: pd.Timestamp, stop: pd.Timestamp) -> str:
    """Submit one area-averaged time-series job and return the CSV text."""
    from harmony import BBox, Collection, Request

    cid, first, last = _collection(spec["short_name"], spec["version"])
    start, stop = max(start, first), min(stop, last)
    if start >= stop:
        raise GiovanniError("Giovanni has no data for these years.")
    west, south, east, north = box
    client = _client()
    req = Request(
        collection=Collection(id=cid),
        temporal={"start": start.to_pydatetime(), "stop": stop.to_pydatetime()},
        spatial=BBox(west, south, east, north),
        variables=[spec["variable"]],
        format="text/csv",
        average="area",
    )
    job = client.submit(req)
    with tempfile.TemporaryDirectory() as tmp:          # keep downloads out of the repo
        paths = [r.result() for r in client.download_all(job, directory=tmp, overwrite=True)]
        if not paths:
            raise GiovanniError("Giovanni returned no file.")
        return Path(paths[0]).read_text(encoding="utf-8")


def parse_giovanni_csv(text: str) -> pd.Series:
    """Giovanni CSV (header block, then time,mean_<variable>) -> monthly Series at month start."""
    lines = text.splitlines()
    start = next((i for i, ln in enumerate(lines) if ln.split(",")[0].strip().strip('"').lower() == "time"), None)
    if start is None:
        raise GiovanniError("Giovanni's answer has no time column.")
    df = pd.read_csv(io.StringIO("\n".join(lines[start:])))
    df.columns = [c.strip() for c in df.columns]
    value_col = next((c for c in df.columns if c.lower().startswith("mean")), df.columns[-1])
    times = pd.to_datetime(df["time"].astype(str).str.strip(), errors="coerce")
    values = pd.to_numeric(df[value_col], errors="coerce")
    s = pd.Series(values.to_numpy(), index=times).dropna()
    s = s[s > -9000]                                    # fill values such as -9999.9
    s.index = s.index.to_period("M").to_timestamp()    # month start
    s = s.groupby(level=0).mean()
    s.index.name = "month"
    return s


# ------------------------------------------------------------------ public

def _fetch_raw(spec: dict, variable: str, box, start_year: int, end_year: int) -> pd.Series:
    """One Giovanni variable, native units, cached."""
    key = cache.make_key("giovanni-area-mean", variable, box, start_year, end_year)
    hit = cache.get(key)
    if hit is None:
        start, stop = pd.Timestamp(f"{start_year}-01-01"), pd.Timestamp(f"{end_year}-12-31 23:59:59")
        errors = []
        for _ in range(ATTEMPTS):
            try:
                text = _run_giovanni({**spec, "variable": variable}, box, start, stop)
                break
            except GiovanniError:
                raise
            except Exception as err:                    # network, auth, quota or job failure
                errors.append(f"{type(err).__name__}: {err}")
        else:
            raise GiovanniError(f"Giovanni failed {ATTEMPTS} times; using one source only. Last error: {errors[-1]}")
        raw = parse_giovanni_csv(text)
        hit = {"variable": variable, "units": spec["native_units"],
               "values": {d.strftime("%Y-%m"): float(v) for d, v in raw.items()}}
        cache.put(key, hit)
    s = pd.Series(hit["values"], dtype="float64")
    s.index = pd.to_datetime(s.index, format="%Y-%m")
    return s


def fetch_series_giovanni(var_id: str, box, start_year: int, end_year: int) -> pd.Series:
    """Monthly area-averaged series for a Giovanni variable, in the units of its POWER twin."""
    spec = GIOVANNI_VARIABLES.get(var_id)
    if spec is None:
        raise GiovanniError(f"No Giovanni variable configured for {var_id!r}.")
    box = tuple(round(float(v), 4) for v in box)
    names = spec.get("variables") or [spec["variable"]]
    parts = [_fetch_raw(spec, v, box, start_year, end_year) for v in names]
    raw = pd.concat(parts, axis=1).mean(axis=1, skipna=False) if len(parts) > 1 else parts[0]
    units, factor = spec["to_units"]
    s = (raw.dropna() * factor + spec.get("offset", 0.0)).sort_index()
    s.index.name = "month"
    s.name = var_id
    s.attrs.update(units=units, source=f"{spec.get('label', var_id)} via Giovanni ({', '.join(names)})")
    return s
