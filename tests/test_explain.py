# SI-assisted: parts of this file were drafted with Claude (Anthropic) and reviewed by the team
"""Plain words + suggestions: offline, Gemini is replaced by fakes. The number check is the safety net."""
import json

import pytest

from td import explain as ex

QUESTIONS = {"hotter": {"label": "Is it getting hotter?", "primary": "T2M"},
             "rain": {"label": "Is rainfall changing?", "primary": "PRECTOTCORR"},
             "drying": {"label": "Is the land drying out?", "primary": "GWETTOP"}}
FACTS = {"question_id": "hotter", "var_id": "T2M",
         "verdict": {"headline": "Air temperature rising about 0.20 °C per decade", "tier": "significant",
                     "rate_per_decade": "+0.20 °C", "years": "1981–2025"},
         "quick_scan": [{"var_id": "PRECTOTCORR", "tier": "none"}, {"var_id": "GWETTOP", "tier": "suggestive"}]}


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("TD_CACHE_DIR", str(tmp_path))
    for k in ("GEMINI_API_KEY", "GOOGLE_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr("td.giovanni._load_env_file", lambda path=None: None)


def test_numbers_check():
    assert ex.numbers_ok("Rising about 0.20 °C per decade since 1981.", json.dumps(FACTS, ensure_ascii=False))
    assert not ex.numbers_ok("Rising 0.3 °C per decade.", json.dumps(FACTS, ensure_ascii=False))


def test_no_key_uses_template_and_ranks_changing_variables_first():
    out = ex.explain(FACTS, QUESTIONS)
    assert out["source"] == "template" and "not its cause" in out["summary"]
    assert out["next"] == ["drying", "rain"]


def test_gemini_text_accepted(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test")
    monkeypatch.setattr(ex, "_call_gemini", lambda p, k: json.dumps(
        {"summary": "It is getting warmer here, about 0.20 °C per decade. We are confident.", "next": ["drying", "bogus"]}))
    out = ex.explain(FACTS, QUESTIONS)
    assert out["source"] == "gemini" and out["next"] == ["drying"]


def test_gemini_invented_number_rejected(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test")
    monkeypatch.setattr(ex, "_call_gemini", lambda p, k: json.dumps({"summary": "Up 2.5 °C by 2050!", "next": []}))
    out = ex.explain(FACTS, QUESTIONS)
    assert out["source"] == "template" and "rejected" in out["why_template"]


def test_gemini_failure_falls_back(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test")

    def boom(p, k):
        raise TimeoutError
    monkeypatch.setattr(ex, "_call_gemini", boom)
    assert ex.explain(FACTS, QUESTIONS)["source"] == "template"


def test_server_scan_and_explain(monkeypatch):
    import pandas as pd

    from td.sample import sample_series
    from web import server

    def _frame(slope):
        return pd.DataFrame({"T2M": sample_series("T2M", slope_decade=slope, seed=1),
                             "PRECTOTCORR": sample_series("PRECTOTCORR", slope_decade=0.0, seed=2),
                             "GWETTOP": sample_series("GWETTOP", slope_decade=0.0, seed=3)})

    monkeypatch.setattr(server, "fetch_points", lambda pts, y0, y1: {pt: _frame(0.4) for pt in pts})
    body = {"points": [[36.5, 10.0]], "years": [1981, 2025]}
    scan = server.quick_scan(body)["scan"]
    assert {s["var_id"] for s in scan} == {"T2M", "PRECTOTCORR", "GWETTOP"}
    assert next(s for s in scan if s["var_id"] == "T2M")["tier"] == "significant"
    out = server.explain_case({**body, "var_id": "T2M", "question_id": "hotter"})
    assert out["summary"] and all(q["id"] != "hotter" for q in out["next"])


def test_unsupported_agreement_or_cause_rejected(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test")
    for text in ("Rising about 0.20 °C per decade. A second NASA dataset agrees.",
                 "Rising about 0.20 °C per decade because of city growth."):
        monkeypatch.setattr(ex, "_call_gemini", lambda p, k, t=text: json.dumps({"summary": t, "next": []}))
        out = ex.explain(FACTS, QUESTIONS)
        assert out["source"] == "template" and "claim" in out["why_template"], text


def test_supported_agreement_and_closing_line_accepted(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test")
    facts = {**FACTS, "cross_check": {"state": "agree", "headline": "Two NASA datasets agree", "detail": ""}}
    monkeypatch.setattr(ex, "_call_gemini", lambda p, k: json.dumps(
        {"summary": "Clearly warmer, about 0.20 °C per decade; a second NASA dataset agrees. "
                    "This shows a change, not its cause.", "next": []}))
    assert ex.explain(facts, QUESTIONS)["source"] == "gemini"
