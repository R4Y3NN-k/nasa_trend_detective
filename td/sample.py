"""Synthetic monthly data with a known trend. TEST AND DEVELOPMENT ONLY: never use it for a demo or screenshot.

Everything made here is marked: series carry attrs["synthetic"] = True and BoxData carries is_synthetic = True,
so the app can show a "SAMPLE DATA" banner.

SI-assisted: parts of this file were drafted with Claude (Anthropic) and reviewed by the team
"""
import numpy as np
import pandas as pd

# mean, seasonal amplitude, peak month, noise sd, noise kind
#   "add": additive noise; "log": multiplicative lognormal noise (sd of log), so rain never goes below zero.
_SHAPES = {
    "T2M": {"mean": 19.0, "amp": 8.0, "peak": 7, "sd": 0.8, "kind": "add"},
    "PRECTOTCORR": {"mean": 1.2, "amp": 0.9, "peak": 1, "sd": 0.4, "kind": "log"},
    "GWETTOP": {"mean": 0.35, "amp": 0.08, "peak": 1, "sd": 0.03, "kind": "add"},
}

BOX_PHI = 0.5           # month-to-month autocorrelation of the noise in sample_box_data
BOX_SHARED_SHARE = 0.8  # share of the noise variance that neighbouring points have in common


def ar1_noise(rng, n, sd, phi):
    """AR(1) noise with stationary standard deviation `sd` and lag-1 autocorrelation `phi` (0 = white)."""
    e = np.empty(n)
    e[0] = rng.normal(0.0, sd)
    step_sd = sd * np.sqrt(1.0 - phi**2)
    for t in range(1, n):
        e[t] = phi * e[t - 1] + rng.normal(0.0, step_sd)
    return e


def _build(var_id, slope_decade, idx, noise, noise_sd) -> pd.Series:
    shape = _SHAPES.get(var_id, _SHAPES["T2M"])
    t_years = np.arange(len(idx)) / 12.0
    expected = (
        shape["mean"]
        + shape["amp"] * np.cos(2 * np.pi * (idx.month.to_numpy() - shape["peak"]) / 12)
        + slope_decade / 10.0 * (t_years - t_years.mean())
    )
    if shape["kind"] == "log":
        # exp(e - sd²/2) has mean 1, so the expected value (and the trend) is unchanged.
        values = np.maximum(expected, 0.0) * np.exp(noise - noise_sd**2 / 2)
    else:
        values = expected + noise
    if var_id == "GWETTOP":
        values = np.clip(values, 0.0, 1.0)
    s = pd.Series(values, index=idx, name=var_id)
    s.attrs["synthetic"] = True
    return s


def sample_series(var_id="T2M", slope_decade=0.3, years=45, seed=0, phi=0.0) -> pd.Series:
    """Seasonal cycle + linear trend of `slope_decade` (units per decade) + AR(1) noise, monthly from Jan 1981."""
    sd = _SHAPES.get(var_id, _SHAPES["T2M"])["sd"]
    idx = pd.date_range("1981-01-01", periods=years * 12, freq="MS")
    noise = ar1_noise(np.random.default_rng(seed), len(idx), sd, phi)
    return _build(var_id, slope_decade, idx, noise, sd)


def sample_box_data(box, seed=0):
    """A synthetic BoxData (is_synthetic=True) for `box` = (west, south, east, north): 3x3 land points.

    Noise = a regional part shared by all points (80% of the variance) + a local part, both AR(1) with phi 0.5,
    so averaging helps only a little, as with real neighbouring grid cells.
    Rain falls in the north of the box and rises in the south, so the zone map has opposite trends to show.
    """
    from td.fetch import BoxData

    west, south, east, north = box
    lats = np.linspace(south, north, 5)[1:4]
    lons = np.linspace(west, east, 5)[1:4]
    idx = pd.date_range("1981-01-01", periods=45 * 12, freq="MS")
    rng = np.random.default_rng(seed)
    shared = {v: ar1_noise(rng, len(idx), s["sd"] * np.sqrt(BOX_SHARED_SHARE), BOX_PHI) for v, s in _SHAPES.items()}
    local_sd = {v: s["sd"] * np.sqrt(1 - BOX_SHARED_SHARE) for v, s in _SHAPES.items()}

    point_data = {}
    for i, lat in enumerate(lats):
        slopes = {"T2M": 0.3, "PRECTOTCORR": 0.08 * (1 - i), "GWETTOP": -0.005}  # rain: south +, north -
        for lon in lons:
            frame = pd.DataFrame({
                v: _build(v, slopes[v], idx, shared[v] + ar1_noise(rng, len(idx), local_sd[v], BOX_PHI), s["sd"])
                for v, s in _SHAPES.items()
            })
            frame.attrs["synthetic"] = True
            point_data[(round(float(lat), 3), round(float(lon), 3))] = frame

    weights = np.array([np.cos(np.radians(lat)) for lat, _ in point_data])
    stacked = np.stack([f.to_numpy() for f in point_data.values()])
    averaged = np.tensordot(weights / weights.sum(), stacked, axes=1)
    first = next(iter(point_data.values()))
    data = pd.DataFrame(averaged, index=first.index, columns=first.columns)
    data.attrs["synthetic"] = True

    points = [(lat, lon, True) for lat, lon in point_data]
    bd = BoxData(data=data, points_total=len(points), points_used=len(points), points=points, point_data=point_data)
    bd.is_synthetic = True
    return bd
