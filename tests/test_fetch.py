# SI-assisted: parts of this file were drafted with Claude (Anthropic) and reviewed by the team
"""Data layer tests (A). Offline: requests.get is replaced by fake answers in POWER's JSON shape."""
import math

import numpy as np
import pytest

from td import cache, fetch
from td.fetch import FetchError, area_mean, fetch_box, grid_points, is_land, parse_power

TUNISIA = (7.5, 30.2, 11.6, 37.5)
SEA = {(36.5, 12.5)}   # pretend this cell is open sea


@pytest.fixture(autouse=True)
def tmp_cache(tmp_path, monkeypatch):
    monkeypatch.setenv("TD_CACHE_DIR", str(tmp_path))
    monkeypatch.setattr(fetch.time, "sleep", lambda s: None)
    return tmp_path


def power_json(lat, lon, start=1981, end=1982, sea=False, gap=None):
    """A fake POWER monthly answer, including month 13 (annual) and a -999 fill value at `gap`."""
    param = {}
    for name in fetch.POWER_PARAMS:
        vals = {}
        for y in range(start, end + 1):
            for m in range(1, 14):
                key = f"{y}{m:02d}"
                if name == "GWETTOP":
                    v = 1.0 if sea else 0.3 + 0.01 * m
                elif name == "T2M":
                    v = 10.0 + m + lat / 10
                else:
                    v = 1.5
                vals[key] = -999.0 if key == gap else v
        param[name] = vals
    return {"type": "Feature", "geometry": {"type": "Point", "coordinates": [lon, lat, 0.0 if sea else 50.0]},
            "properties": {"parameter": param}, "header": {"fill_value": -999.0}}


class FakeResponse:
    def __init__(self, status, js=None):
        self.status_code, self._js = status, js

    def json(self):
        return self._js


@pytest.fixture
def fake_power(monkeypatch):
    """Answers like POWER; records every call. Set .fail_first = n to make the first n calls fail with 429."""
    class Fake:
        calls, fail_first, gap = [], 0, None

        def __call__(self, url, params, timeout):
            self.calls.append((params["latitude"], params["longitude"]))
            if len(self.calls) <= self.fail_first:
                return FakeResponse(429)
            lat, lon = params["latitude"], params["longitude"]
            return FakeResponse(200, power_json(lat, lon, params["start"], params["end"],
                                                sea=(lat, lon) in SEA, gap=self.gap))
    fake = Fake()
    fake.calls = []
    monkeypatch.setattr(fetch.requests, "get", fake)
    return fake


def test_cache_roundtrip_and_key():
    assert cache.get("missing") is None
    k = cache.make_key("power", 36.5, 10.0, 1981, 2025)
    assert k == cache.make_key("power", 36.5, 10.0, 1981, 2025) and len(k) == 40
    assert k != cache.make_key("power", 36.5, 10.625, 1981, 2025)
    cache.put(k, {"a": [1, None]})
    assert cache.get(k) == {"a": [1, None]}


def test_grid_tunisia_has_about_28_distinct_merra2_points_inside_box():
    pts = grid_points(TUNISIA)
    assert 20 <= len(pts) <= 30 and len(set(pts)) == len(pts)
    for lat, lon in pts:
        assert TUNISIA[1] - 0.25 <= lat <= TUNISIA[3] + 0.25 and TUNISIA[0] - 0.32 <= lon <= TUNISIA[2] + 0.32
        assert math.isclose(lat / 0.5, round(lat / 0.5)) and math.isclose((lon + 180) / 0.625, round((lon + 180) / 0.625))


def test_grid_small_and_huge_boxes():
    assert len(grid_points((9.8, 36.5, 10.6, 37.1))) == 1            # Tunis governorate
    assert len(grid_points((-20, -35, 20, 5))) <= 30                 # 40 x 40 degrees
    with pytest.raises(FetchError):
        grid_points((11.0, 30.0, 10.0, 31.0))


def test_parse_skips_annual_and_fill_values():
    df = parse_power(power_json(36.5, 10.0, gap="198103"))
    assert len(df) == 24 and list(df.columns) == list(fetch.POWER_PARAMS)
    assert str(df.index[0].date()) == "1981-01-01" and np.isnan(df.loc["1981-03-01", "T2M"])
    assert df.isna().sum().tolist() == [1] * len(fetch.POWER_PARAMS) and df["PRECTOTCORR"].dropna().eq(1.5).all()


def test_land_mask():
    assert is_land(parse_power(power_json(36.5, 10.0)))
    assert not is_land(parse_power(power_json(36.5, 12.5, sea=True)))      # saturated topsoil all year
    all_missing = parse_power(power_json(36.5, 12.5))
    all_missing["GWETTOP"] = np.nan
    assert not is_land(all_missing)


def test_area_mean_cos_latitude_weights_skip_gaps():
    a = parse_power(power_json(0.0, 10.0))[["T2M"]] * 0 + 10.0
    b = parse_power(power_json(60.0, 10.0))[["T2M"]] * 0 + 40.0
    b.iloc[1] = np.nan
    out = area_mean({(0.0, 10.0): a, (60.0, 10.0): b})["T2M"]
    w = math.cos(math.radians(60))
    assert out.iloc[0] == pytest.approx((10 + 40 * w) / (1 + w)) and out.iloc[1] == pytest.approx(10.0)


def test_fetch_box_end_to_end_with_fake_power(fake_power):
    box = (10.0, 36.3, 13.0, 36.7)
    pts = grid_points(box)
    assert SEA & set(pts), "test box must include the fake sea cell"
    bd = fetch_box(box, 1981, 1982)
    assert bd.points_total == len(pts) and bd.points_used == len(pts) - 1
    assert [(la, lo) for la, lo, land in bd.points if not land] == list(SEA)
    assert set(bd.point_data) == {(la, lo) for la, lo, land in bd.points if land}
    assert list(bd.data.columns) == ["T2M", "PRECTOTCORR", "GWETTOP"] and len(bd.data) == 24
    assert str(bd.data.index[0].date()) == "1981-01-01" and not bd.data.isna().any().any()


def test_answers_are_cached_and_429_is_retried(fake_power):
    fake_power.fail_first = 2
    fetch.fetch_point(36.5, 10.0, 1981, 1982)
    assert len(fake_power.calls) == 3                      # two 429s, then success
    fetch.fetch_point(36.5, 10.0, 1981, 1982)
    assert len(fake_power.calls) == 3                      # second time from the cache


def test_errors_are_fetch_errors(fake_power, monkeypatch):
    with pytest.raises(FetchError, match="no land"):
        fetch_box((12.2, 36.3, 12.7, 36.7), 1981, 1982)    # only the fake sea cell
    monkeypatch.setattr(fetch.requests, "get", lambda url, params, timeout: FakeResponse(503))
    with pytest.raises(FetchError, match="did not answer"):
        fetch_box((8.0, 33.0, 8.4, 33.4), 1981, 1982)


def test_elevation_is_kept_per_point(fake_power):
    df = parse_power(power_json(36.5, 10.0))
    assert df.attrs["elevation_m"] == 50.0
    bd = fetch_box((10.0, 36.3, 13.0, 36.7), 1981, 1982)
    elev = fetch.elevations(bd.point_data)
    assert set(elev) == set(bd.point_data) and all(v == 50.0 for v in elev.values())
