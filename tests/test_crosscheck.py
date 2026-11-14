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
