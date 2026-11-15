# SI-assisted: parts of this file were drafted with Claude (Anthropic) and reviewed by the team
"""UI-pass additions to the web API (decade bars, seasons, has_second_source): offline, synthetic series."""
import numpy as np
import pandas as pd
import pytest

from td.sample import sample_series
from web import server


def _frame(slope):
    return pd.DataFrame({"T2M": sample_series("T2M", slope_decade=slope, seed=1),
                         "PRECTOTCORR": sample_series("PRECTOTCORR", slope_decade=0.0, seed=2),
                         "GWETTOP": sample_series("GWETTOP", slope_decade=0.0, seed=3)})


@pytest.fixture
def land_points(monkeypatch):
    monkeypatch.setattr(server, "fetch_points", lambda pts, y0, y1: {pt: _frame(0.4) for pt in pts})


BODY = {"points": [[36.5, 10.0], [36.0, 10.0]], "var_id": "T2M", "years": [1981, 2025]}


def _row(label, slope, lo, hi, tier="significant"):
    return {"label": label, "slope_decade": slope, "ci_decade": [lo, hi], "tier": tier}


def test_decade_means_follow_a_known_trend():
    idx = pd.date_range("1981-01-01", "2025-12-01", freq="MS")
    years = idx.year + (idx.month - 1) / 12
    anom = pd.Series(0.03 * (years - 2003.5), index=idx)          # +0.3 per decade, mean zero
    d = server.decade_means(anom)
    assert [x["decade"] for x in d] == ["1980s", "1990s", "2000s", "2010s", "2020s"]
    means = [x["mean"] for x in d]
    assert means == sorted(means)                                  # rises decade after decade
    assert means[2] - means[1] == pytest.approx(0.3, abs=0.01)     # ten years apart = one decade of trend
    assert d[0]["first_year"] == 1981 and d[0]["months"] == 108 and d[-1]["last_year"] == 2025


def test_decade_means_skip_short_decades_and_gaps():
    idx = pd.date_range("1989-06-01", "2001-12-01", freq="MS")
    anom = pd.Series(1.0, index=idx)
    anom.iloc[10:14] = np.nan
    d = server.decade_means(anom)
    assert [x["decade"] for x in d] == ["1990s", "2000s"]          # 7 months of the 1980s are not a decade
    assert d[0]["months"] == 116


def test_analyze_reports_decades_and_second_source(land_points):
    out = server.run_analysis(BODY)
    assert out["has_second_source"] is True
    assert len(out["decades"]) == 5 and out["decades"][-1]["mean"] > out["decades"][0]["mean"]
    assert len(out["annual"]["year"]) == 45 == len(out["annual"]["value"])
    assert server.run_analysis({**BODY, "var_id": "GWETTOP"})["has_second_source"] is False


def test_seasons_run_the_same_tests_per_season(land_points):
    out = server.seasonal_trends(BODY)
    assert [s["id"] for s in out["seasons"]] == ["DJF", "MAM", "JJA", "SON"]
    assert out["hemisphere"] == "north" and out["seasons"][0]["label"] == "Winter"
    for s in out["seasons"]:
        assert s["tier"] == "significant" and s["slope_decade"] == pytest.approx(0.4, abs=0.15)
        assert s["n_months"] == 135
    assert "per decade" in out["sentence"] and "caused" not in out["sentence"]


def test_seasons_flip_names_south_of_the_equator(land_points):
    out = server.seasonal_trends({**BODY, "points": [[-33.5, 18.75]]})
    assert out["hemisphere"] == "south" and out["seasons"][0]["label"] == "Summer"


def test_season_sentence_only_says_faster_when_ranges_do_not_overlap():
    apart = server.season_sentence([_row("Winter", 0.6, 0.5, 0.7), _row("Summer", 0.2, 0.1, 0.3)], "Air temperature", "°C", 2)
    assert "fastest" in apart and "clearly more" in apart
    overlap = server.season_sentence([_row("Winter", 0.6, 0.2, 1.0), _row("Summer", 0.4, 0.1, 0.7)], "Air temperature", "°C", 2)
    assert "overlap" in overlap and "fastest" not in overlap
    none = server.season_sentence([_row("Winter", 0.1, -0.2, 0.4, "none"), _row("Summer", 0.0, -0.3, 0.3, "none")], "Rain", "mm/day", 2)
    assert none.startswith("No single season")


def test_compare_areas_two_places_same_variable(monkeypatch):
    fast, slow = {(36.5, 10.0), (36.0, 10.0)}, {(50.0, -97.5), (50.5, -97.5)}
    monkeypatch.setattr(server, "fetch_points",
                        lambda pts, y0, y1: {pt: _frame(0.8 if pt in fast else 0.0) for pt in pts})
    out = server.compare_areas({"var_id": "T2M", "years": [1981, 2025],
                                "a": {"name": "Tunis", "points": [list(p) for p in fast]},
                                "b": {"name": "Manitoba", "points": [list(p) for p in slow]}})
    assert out["a"]["name"] == "Tunis" and out["b"]["name"] == "Manitoba"
    assert out["a"]["res"]["slope_decade"] > out["b"]["res"]["slope_decade"]
    assert "Tunis" in out["sentence"] and "Manitoba" in out["sentence"]
    assert out["a"]["decades"] and len(out["b"]["annual"]["year"]) == 45
    assert "_res" not in out["a"]


def test_compare_areas_rejects_an_unknown_variable(land_points):
    with pytest.raises(server.FetchError):
        server.compare_areas({"var_id": "NOPE", "a": {"points": BODY["points"]}, "b": {"points": BODY["points"]}})
