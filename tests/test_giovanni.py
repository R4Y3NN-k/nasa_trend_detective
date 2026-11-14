# SI-assisted: parts of this file were drafted with Claude (Anthropic) and reviewed by the team
"""Giovanni (step 7) tests (A). Offline: the Giovanni job is replaced by a fake CSV."""
import pytest

from td import giovanni
from td.fetch import FetchError

FAKE_CSV = """Title:,Area-Averaged Time Series (Region: 7.5E 30.2N 11.6E 37.5N)
User Start Date:,2000-06-01T00:00:00Z
User End Date:,2000-09-30T23:59:59Z
Fill Value (mean_GPM_3IMERGM_07_precipitation):,-9999.9

time,mean_GPM_3IMERGM_07_precipitation
2000-06-01 00:00:00,0.0125
2000-07-01 00:00:00,0.0050
2000-08-01 00:00:00,-9999.9
2000-09-01 00:00:00,0.0300
"""


@pytest.fixture(autouse=True)
def tmp_cache(tmp_path, monkeypatch):
    monkeypatch.setenv("TD_CACHE_DIR", str(tmp_path))


def test_parse_giovanni_csv_skips_header_and_fill():
    s = giovanni.parse_giovanni_csv(FAKE_CSV)
    assert [d.strftime("%Y-%m") for d in s.index] == ["2000-06", "2000-07", "2000-09"]
    assert s.iloc[0] == pytest.approx(0.0125)


def test_fetch_converts_to_mm_per_day_and_caches(monkeypatch):
    calls = []
    monkeypatch.setattr(giovanni, "_run_giovanni", lambda spec, box, a, b: calls.append(box) or FAKE_CSV)
    s = giovanni.fetch_series_giovanni("IMERG", (7.5, 30.2, 11.6, 37.5), 2000, 2000)
    assert s.iloc[0] == pytest.approx(0.0125 * 24) and s.attrs["units"] == "mm/day"
    giovanni.fetch_series_giovanni("IMERG", (7.5, 30.2, 11.6, 37.5), 2000, 2000)
    assert len(calls) == 1                                   # second call from the cache


def test_gives_up_after_two_failures_with_a_fetch_error(monkeypatch):
    calls = []

    def boom(spec, box, a, b):
        calls.append(1)
        raise ConnectionError("Giovanni down")

    monkeypatch.setattr(giovanni, "_run_giovanni", boom)
    with pytest.raises(FetchError, match="failed 2 times"):
        giovanni.fetch_series_giovanni("IMERG", (7.5, 30.2, 11.6, 37.5), 2000, 2001)
    assert len(calls) == 2
    with pytest.raises(giovanni.GiovanniError):
        giovanni.fetch_series_giovanni("T2M", (7.5, 30.2, 11.6, 37.5), 2000, 2001)


def test_missing_login_is_a_clear_error(monkeypatch, tmp_path):
    for k in ("EARTHDATA_USERNAME", "EARTHDATA_PASSWORD", "EARTHDATA_TOKEN"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr(giovanni, "ENV_FILE", tmp_path / "no.env")
    monkeypatch.setattr(giovanni, "_load_env_file", lambda path=None: None)
    with pytest.raises(giovanni.GiovanniError, match="Earthdata Login"):
        giovanni._client()


AIRS_CSV = """Title:,Area-Averaged Time Series
time,mean_AIRS3STM_7_0_SurfAirTemp_{p}
2003-01-01 00:00:00,{a}
2003-02-01 00:00:00,{b}
"""


def test_airs_averages_day_and_night_and_converts_to_celsius(monkeypatch):
    fake = {"AIRS3STM_7_0_SurfAirTemp_A": AIRS_CSV.format(p="A", a=300.15, b=302.15),
            "AIRS3STM_7_0_SurfAirTemp_D": AIRS_CSV.format(p="D", a=290.15, b=292.15)}
    monkeypatch.setattr(giovanni, "_run_giovanni", lambda spec, box, a, b: fake[spec["variable"]])
    s = giovanni.fetch_series_giovanni("AIRS_T", (7.5, 30.2, 11.6, 37.5), 2003, 2003)
    assert list(s.round(6)) == [22.0, 24.0]                  # (300.15 + 290.15) / 2 - 273.15
    assert s.attrs["units"] == "°C" and "AIRS" in s.attrs["source"]
