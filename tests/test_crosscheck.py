# SI-assisted: parts of this file were drafted with Claude (Anthropic) and reviewed by the team
"""Cross-check (step 7) in the web API: offline, NASA POWER and Giovanni are replaced by synthetic series."""
import pandas as pd
import pytest

from td.fetch import FetchError
from td.sample import sample_series
from web import server


def _frame(slope):
    return pd.DataFrame({"T2M": sample_series("T2M", slope_decade=slope, seed=1),
                         "PRECTOTCORR": sample_series("PRECTOTCORR", slope_decade=0.0, seed=2),
                         "GWETTOP": sample_series("GWETTOP", slope_decade=0.0, seed=3)})


@pytest.fixture
def one_land_point(monkeypatch):
    monkeypatch.setattr(server, "fetch_points", lambda pts, y0, y1: {pt: _frame(0.4) for pt in pts})


BODY = {"points": [[36.5, 10.0]], "var_id": "T2M", "years": [1981, 2025]}


def _airs(slope, seed):
    s = sample_series("T2M", slope_decade=slope, seed=seed)
    return s[s.index >= "2002-09-01"]


def test_crosscheck_agree(monkeypatch, one_land_point):
    import td.giovanni as g
    monkeypatch.setattr(g, "fetch_series_giovanni", lambda vid, box, y0, y1: _airs(0.4, 7))
    out = server.cross_check(BODY)
    assert out["state"] == "agree"
    assert out["years"][0] == 2002 and out["sources"][1]["label"].startswith("AIRS")
    assert out["figure"]["data"] and "Two NASA datasets agree" == out["headline"]


def test_crosscheck_disagree(monkeypatch, one_land_point):
    import td.giovanni as g
    monkeypatch.setattr(g, "fetch_series_giovanni", lambda vid, box, y0, y1: _airs(-0.8, 8))
    assert server.cross_check(BODY)["state"] == "disagree"


def test_crosscheck_survives_giovanni_failure(monkeypatch, one_land_point):
    import td.giovanni as g

    def boom(*a):
        raise g.GiovanniError("Giovanni needs an Earthdata Login.")
    monkeypatch.setattr(g, "fetch_series_giovanni", boom)
    out = server.cross_check(BODY)
    assert out["state"] == "single" and "Earthdata" in out["detail"]


def test_crosscheck_variable_without_second_source(one_land_point):
    assert server.cross_check({**BODY, "var_id": "GWETTOP"})["state"] == "none"


def test_crosscheck_bad_request_is_a_fetch_error():
    with pytest.raises(FetchError):
        server.cross_check({"points": [], "var_id": "T2M"})


# ---------------------------------------------------------------- highland vs lowland (jury remark)

def _land(elev, slope, seed):
    df = pd.DataFrame({"T2M": sample_series("T2M", slope_decade=slope, seed=seed),
                       "PRECTOTCORR": sample_series("PRECTOTCORR", slope_decade=0.0, seed=seed + 50),
                       "GWETTOP": sample_series("GWETTOP", slope_decade=0.0, seed=seed + 90)})
    df.attrs["elevation_m"] = elev
    return df


MONTHS = pd.date_range("1981-01-01", "2025-12-01", freq="MS", name="month")


def test_elevation_split_finds_faster_warming_mountains():
    land = {(36.0 + i * 0.5, 10.0): _land(2500.0, 0.9, i) for i in range(3)}
    land.update({(30.0 + i * 0.5, 10.0): _land(100.0, 0.1, 10 + i) for i in range(3)})
    out = server.elevation_split(land, MONTHS, "T2M")
    assert out["applies"] and out["high"]["points"] == 3 and out["low"]["points"] == 3
    assert "Higher ground" in out["sentence"] and "faster" in out["sentence"]


def test_flat_area_says_one_trend_fits():
    land = {(36.0 + i * 0.5, 10.0): _land(100.0 + 20 * i, 0.3, i) for i in range(4)}
    out = server.elevation_split(land, MONTHS, "T2M")
    assert out["applies"] is False and "one trend" in out["sentence"]


def test_too_few_points_or_no_elevation_skips():
    assert server.elevation_split({(36.0, 10.0): _land(None, 0.3, 1)}, MONTHS, "T2M") is None


# ---------------------------------------------------------------- groups (2D / 3D)

def test_groups_split_points_that_change_differently(monkeypatch):
    north = {(37.0 + 0.5 * i, 10.0): _land(100.0, 0.8, i) for i in range(4)}
    south = {(33.0 + 0.5 * i, 10.0): _land(100.0, -0.2, 20 + i) for i in range(4)}
    frames = {**north, **south}
    monkeypatch.setattr(server, "fetch_points", lambda pts, y0, y1: {pt: frames[pt] for pt in pts})
    out = server.cluster_view({"points": [list(p) for p in frames], "years": [1981, 2025]})
    assert out["ok"] and len(out["zones"]) >= 2
    assert {p["zone"] for p in out["points"] if p["lat"] >= 37} != {p["zone"] for p in out["points"] if p["lat"] < 37}
    assert out["figure2d"]["data"] and out["figure3d"]["data"][0]["type"] == "scatter3d"
    assert [f["id"] for f in out["features"]][:2] == ["T2M", "PRECTOTCORR"]


def test_groups_need_four_land_points(monkeypatch):
    monkeypatch.setattr(server, "fetch_points", lambda pts, y0, y1: {pt: _land(100.0, 0.3, 1) for pt in pts})
    out = server.cluster_view({"points": [[36.0, 10.0], [36.5, 10.0]], "years": [1981, 2025]})
    assert not out["ok"] and "at least 4" in out["reason"]


# ---------------------------------------------------------------- decades, seasons, second-source flag, nearest

def test_analysis_carries_decades_seasons_and_second_source_flag(monkeypatch, one_land_point):
    out = server.run_analysis(BODY)
    assert out["has_second_source"] is True
    assert [d["label"] for d in out["decades"]] == ["1980s", "1990s", "2000s", "2010s", "2020s"]
    assert out["decades"][0]["mean"] < out["decades"][-1]["mean"]            # +0.4 per decade series
    assert abs(sum(d["mean"] * d["months"] for d in out["decades"])) < 1e-6  # anomalies average to zero
    assert len(out["seasons"]["rows"]) == 4 and out["seasons"]["rows"][0]["name"].startswith("Winter")
    assert server.run_analysis({**BODY, "var_id": "GWETTOP"})["has_second_source"] is False


def test_season_names_follow_the_hemisphere():
    s = sample_series("T2M", slope_decade=0.4, seed=1)
    assert server.season_trends(s, "T2M", -30.0)["rows"][0]["name"].startswith("Summer")
    assert server.season_trends(s, "T2M", 2.0)["rows"][0]["name"] == "Dec–Feb"


def test_nearest_endpoint_uses_land_cells_only(monkeypatch):
    def fake_fetch(lat, lon, y0, y1):
        df = _frame(0.1)
        if lon < 10.0:
            df["GWETTOP"] = 1.0                                              # sea
        return df
    monkeypatch.setattr(server, "fetch_point", fake_fetch)
    out = server.nearest_cells({"center": [36.0, 9.4], "k": 4})
    assert len(out["cells"]) == 4 and all(lon >= 10.0 for _, lon in out["cells"])
    with pytest.raises(FetchError):
        server.nearest_cells({"center": "x"})
