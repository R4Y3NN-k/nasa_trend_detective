# SI-assisted: parts of this file were drafted with Claude (Anthropic) and reviewed by the team
import numpy as np
import pytest

from td.analyze import analyze, anomalies, correlate, verdict
from td.sample import sample_series


def test_known_slope_comes_back_and_is_significant():
    res = analyze(sample_series("T2M", slope_decade=0.3, seed=0), "T2M")
    assert res["slope_decade"] == pytest.approx(0.3, abs=0.05)
    assert res["sen_decade"] == pytest.approx(0.3, abs=0.05)
    lo, hi = res["ci_decade"]
    assert lo < 0.3 < hi
    assert res["tier"] == "significant"
    assert res["tests_agree"]
    assert res["years_to_significance"] == 0.0


def test_falling_trend_is_negative():
    res = analyze(sample_series("T2M", slope_decade=-0.3, seed=1), "T2M")
    assert res["slope_decade"] < 0
    assert res["tier"] == "significant"
    assert "falling" in verdict(res)["headline"]


def test_flat_series_is_rarely_significant():
    hits = sum(analyze(sample_series("T2M", slope_decade=0.0, seed=s), "T2M")["tier"] == "significant" for s in range(40))
    assert hits <= 4


def test_anomalies_remove_the_seasons():
    anom = anomalies(sample_series("T2M", slope_decade=0.0, seed=2))
    monthly_means = anom.groupby(anom.index.month).mean()
    assert np.allclose(monthly_means, 0.0, atol=1e-9)


def test_missing_months_are_counted_and_handled():
    s = sample_series("T2M", slope_decade=0.3, seed=3)
    gaps = s.index[np.random.default_rng(3).choice(np.arange(1, len(s) - 1), size=30, replace=False)]
    with_nan = s.copy()
    with_nan[gaps] = np.nan
    dropped = s.drop(gaps[:10])

    res_nan = analyze(with_nan, "T2M")
    res_dropped = analyze(dropped, "T2M")
    assert res_nan["missing_months"] == 30
    assert res_dropped["missing_months"] == 10
    assert res_nan["n_months"] == len(s) - 30
    assert res_nan["slope_decade"] == pytest.approx(0.3, abs=0.05)


def test_too_short_record_raises():
    with pytest.raises(ValueError):
        analyze(sample_series("T2M").iloc[:12], "T2M")


def test_short_record_flag():
    assert analyze(sample_series("T2M", years=20), "T2M")["short_record"]
    assert not analyze(sample_series("T2M", years=45), "T2M")["short_record"]


def test_percent_per_decade_only_for_relative_variables():
    assert analyze(sample_series("T2M"), "T2M")["pct_decade"] is None
    rain = analyze(sample_series("PRECTOTCORR", slope_decade=0.1, seed=4), "PRECTOTCORR")
    assert rain["pct_decade"] == pytest.approx(rain["slope_decade"] / rain["mean"] * 100)


def test_years_to_significance_for_a_weak_trend():
    res = analyze(sample_series("T2M", slope_decade=0.01, seed=5), "T2M")
    assert res["tier"] != "significant"
    assert res["years_to_significance"] is None or res["years_to_significance"] > 0


def test_result_has_all_contract_keys():
    res = analyze(sample_series("T2M"), "T2M")
    expected = {
        "var_id", "start", "end", "n_months", "missing_months", "span_years", "mean", "slope_decade", "ci_decade",
        "p_ttest", "p_mk", "sen_decade", "tier", "tests_agree", "total_change", "pct_decade",
        "years_to_significance", "short_record", "_anomalies", "_trend_line",
    }
    assert expected <= set(res)
    assert res["start"] == "1981-01" and res["end"] == "2025-12"


def test_verdict_words():
    sig = verdict(analyze(sample_series("T2M", slope_decade=0.3, seed=0), "T2M"))
    assert sig["headline"].startswith("Air temperature rising about 0.")
    assert "per decade" in sig["headline"]
    assert "cause" in sig["detail"]

    flat = analyze(sample_series("T2M", slope_decade=0.0, seed=6), "T2M")
    if flat["tier"] == "none":
        assert verdict(flat)["headline"] == "No clear trend yet"


def test_correlate():
    a = sample_series("T2M", seed=7)
    assert correlate(a, a)["r"] == pytest.approx(1.0)
    assert correlate(a, -a)["r"] == pytest.approx(-1.0)
    unrelated = correlate(a, sample_series("T2M", seed=8))
    assert abs(unrelated["r"]) < 0.5
    assert unrelated["n"] == len(a)


def test_sample_box_data_shape():
    pytest.importorskip("td.fetch", reason="td/fetch.py (BoxData) not on main yet")
    from td.sample import sample_box_data

    bd = sample_box_data((7.5, 30.2, 11.6, 37.5))
    assert list(bd.data.columns) == ["T2M", "PRECTOTCORR", "GWETTOP"]
    assert bd.points_used == len(bd.point_data) == 9
    north = analyze(bd.point_data[max(bd.point_data)]["PRECTOTCORR"], "PRECTOTCORR")
    south = analyze(bd.point_data[min(bd.point_data)]["PRECTOTCORR"], "PRECTOTCORR")
    assert north["slope_decade"] < 0 < south["slope_decade"]
