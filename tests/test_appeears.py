# SI-assisted: parts of this file were drafted with Claude (Anthropic) and reviewed by the team
"""AppEEARS NDVI (step 8) tests (A). Offline: requests are replaced by fake AppEEARS answers."""
import pytest

from td import appeears
from td.fetch import FetchError

STATS_CSV = """File Name,Dataset,aid,Date,Count,Minimum,Maximum,Range,Mean,Standard Deviation
f1,_250m_16_days_NDVI,aid0001,2001-01-01,900,0.05,0.8,0.75,0.30,0.1
f2,_250m_16_days_NDVI,aid0001,2001-01-17,900,0.05,0.8,0.75,0.40,0.1
f3,_250m_16_days_pixel_reliability,aid0001,2001-01-17,900,0,3,3,1.2,0.5
f4,_250m_16_days_NDVI,aid0001,2001-02-02,900,0.05,0.8,0.75,0.50,0.1
"""


class Resp:
    def __init__(self, status=200, js=None, text=""):
        self.status_code, self._js, self.text = status, js, text

    def json(self):
        return self._js


@pytest.fixture(autouse=True)
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("TD_CACHE_DIR", str(tmp_path))
    monkeypatch.setenv("EARTHDATA_USERNAME", "test-user")
    monkeypatch.setenv("EARTHDATA_PASSWORD", "test-pass")


def fake_api(monkeypatch, status="done"):
    calls = []
    monkeypatch.setattr(appeears.requests, "post", lambda url, auth, timeout: Resp(js={"token": "tok"}))

    def get(url, headers, timeout, allow_redirects):
        calls.append(url)
        if url.endswith("/task/T1"):
            return Resp(js={"status": status})
        if url.endswith("/bundle/T1"):
            return Resp(js={"files": [{"file_id": "a", "file_name": "T1-granule-list.txt"},
                                      {"file_id": "b", "file_name": "MOD13Q1-061-Statistics.csv"}]})
        if url.endswith("/bundle/T1/b"):
            return Resp(text=STATS_CSV)
        return Resp(status=404)
    monkeypatch.setattr(appeears.requests, "get", get)
    return calls


def test_parse_keeps_ndvi_layer_and_averages_months():
    s = appeears.parse_ndvi_csv(STATS_CSV)
    assert [d.strftime("%Y-%m") for d in s.index] == ["2001-01", "2001-02"]
    assert s.iloc[0] == pytest.approx(0.35) and s.iloc[1] == pytest.approx(0.50)


def test_unscaled_values_are_scaled():
    s = appeears.parse_ndvi_csv(STATS_CSV.replace(",0.30,", ",3000,").replace(",0.40,", ",4000,")
                                .replace(",0.50,", ",5000,"))
    assert s.iloc[0] == pytest.approx(0.35)


def test_load_ndvi_downloads_once_then_uses_cache(monkeypatch):
    calls = fake_api(monkeypatch)
    s = appeears.load_ndvi("T1")
    assert s.name == "NDVI" and s.iloc[0] == pytest.approx(0.35)
    n = len(calls)
    appeears.load_ndvi("T1")
    assert len(calls) == n


def test_unfinished_task_is_a_fetch_error(monkeypatch):
    fake_api(monkeypatch, status="processing")
    with pytest.raises(FetchError, match="not done yet"):
        appeears.load_ndvi("T1")
