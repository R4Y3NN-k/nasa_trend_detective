"""Synthetic monthly data with a known trend, so the app and tests can run before real NASA data exists.

SI-assisted: parts of this file were drafted with Claude (Anthropic) and reviewed by the team
"""
import numpy as np
import pandas as pd

# (long-term mean, seasonal amplitude, monthly noise sd, lower bound, upper bound)
_SHAPES = {
    "T2M": (19.0, 8.0, 0.8, None, None),
    "PRECTOTCORR": (1.2, 0.9, 0.35, 0.0, None),
    "GWETTOP": (0.35, 0.08, 0.03, 0.0, 1.0),
}


def sample_series(var_id="T2M", slope_decade=0.3, years=45, seed=0) -> pd.Series:
    """Seasonal cycle + linear trend of `slope_decade` (variable units per decade) + white noise, from Jan 1981."""
    mean, amp, noise, lo, hi = _SHAPES.get(var_id, _SHAPES["T2M"])
    rng = np.random.default_rng(seed)
    idx = pd.date_range("1981-01-01", periods=years * 12, freq="MS")
    t_years = np.arange(len(idx)) / 12.0
    values = (
        mean
        + amp * np.cos(2 * np.pi * (idx.month.to_numpy() - 7) / 12)
        + slope_decade / 10.0 * (t_years - t_years.mean())
        + rng.normal(0.0, noise, len(idx))
    )
    if lo is not None or hi is not None:
        values = np.clip(values, lo, hi)
    return pd.Series(values, index=idx, name=var_id)


def sample_box_data(box):
    """A BoxData for `box` = (west, south, east, north) on a 3x3 grid of land points.

    Rain falls in the north of the box and rises in the south, so the zone map has opposite trends to show.
    """
    from td.fetch import BoxData

    west, south, east, north = box
    lats = np.linspace(south, north, 5)[1:4]
    lons = np.linspace(west, east, 5)[1:4]

    point_data = {}
    seed = 0
    for i, lat in enumerate(lats):
        rain_slope = 0.08 * (1 - i)  # south +0.08, middle 0, north -0.08 mm/day per decade
        for lon in lons:
            frame = pd.DataFrame({
                "T2M": sample_series("T2M", 0.3, seed=seed),
                "PRECTOTCORR": sample_series("PRECTOTCORR", rain_slope, seed=seed + 1),
                "GWETTOP": sample_series("GWETTOP", -0.005, seed=seed + 2),
            })
            point_data[(round(float(lat), 3), round(float(lon), 3))] = frame
            seed += 3

    weights = np.array([np.cos(np.radians(lat)) for lat, _ in point_data])
    stacked = np.stack([f.to_numpy() for f in point_data.values()])
    averaged = np.tensordot(weights / weights.sum(), stacked, axes=1)
    first = next(iter(point_data.values()))
    data = pd.DataFrame(averaged, index=first.index, columns=first.columns)

    points = [(lat, lon, True) for lat, lon in point_data]
    return BoxData(data=data, points_total=len(points), points_used=len(points), points=points, point_data=point_data)
