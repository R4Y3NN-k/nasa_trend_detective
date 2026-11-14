# SI-assisted: parts of this file were drafted with Claude (Anthropic) and reviewed by the team
import numpy as np
import pytest

from td import analyze as analyze_module
from td import report, sample, trendmap
from td.analyze import MIN_MONTHS, analyze, anomalies, correlate, verdict
from td.sample import sample_box_data, sample_series

N_CALIBRATION = 200


def test_contracts_exist():
    for name in ("anomalies", "analyze", "verdict", "correlate", "compare", "agreement"):
        assert callable(getattr(analyze_module, name))
    assert callable(trendmap.trend_grid)
    assert callable(sample.sample_series) and callable(sample.sample_box_data)
    assert callable(report.markdown_report) and callable(report.csv_bytes)


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


def test_false_significant_rate_on_flat_series():
    """Ideal is 5% or less; measured 7.0% on these 200 seeds (see docs/validation.md). Guards against regressions."""
    hits = sum(analyze(sample_series("T2M", 0.0, seed=s), "T2M")["tier"] == "significant" for s in range(N_CALIBRATION))
    assert hits / N_CALIBRATION <= 0.08


def test_ci_coverage_with_autocorrelated_noise():
    """Ideal is 95%; measured 92.5% with AR(1) phi = 0.5 on these 200 seeds (see docs/validation.md)."""
    covered = 0
    for s in range(N_CALIBRATION):
        lo, hi = analyze(sample_series("T2M", 0.3, seed=10_000 + s, phi=0.5), "T2M")["ci_decade"]
        covered += lo <= 0.3 <= hi
    assert covered / N_CALIBRATION >= 0.90


def test_mann_kendall_fallback_when_hamed_rao_gives_nan():
    # Flat series, strong autocorrelation: Hamed-Rao's variance correction goes negative for this seed.
    res = analyze(sample_series("T2M", 0.0, seed=67, phi=0.8), "T2M")
    assert res["mk_fallback"]
    assert np.isfinite(res["p_mk"]) and res["p_mk"] > 0.05
    assert "pre-whitened" in verdict(res)["detail"]
    assert not analyze(sample_series("T2M", 0.3, seed=0), "T2M")["mk_fallback"]


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


def test_record_needs_at_least_60_months():
    assert MIN_MONTHS == 60
    with pytest.raises(ValueError):
        analyze(sample_series("T2M").iloc[:59], "T2M")
    assert analyze(sample_series("T2M").iloc[:60], "T2M")["n_months"] == 60


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


# ---------- sample data (test-only) ----------

def test_sample_data_is_marked_synthetic():
    assert sample_series("T2M").attrs["synthetic"] is True
    bd = sample_box_data((7.5, 30.2, 11.6, 37.5))
    assert bd.is_synthetic is True
    assert all(f["T2M"].attrs.get("synthetic") for f in bd.point_data.values())
    assert bd.data["PRECTOTCORR"].attrs.get("synthetic")


def test_sample_seasons_peak_in_the_right_month():
    for var_id, peak in (("T2M", 7), ("PRECTOTCORR", 1), ("GWETTOP", 1)):
        s = sample_series(var_id, 0.0, seed=1)
        assert s.groupby(s.index.month).mean().idxmax() in {peak - 1 or 12, peak, peak % 12 + 1}, var_id


def test_sample_rain_is_never_clipped_at_zero():
    for seed in range(5):
        assert (sample_series("PRECTOTCORR", 0.1, seed=seed) > 0).all()


def test_sample_ar1_noise_has_the_requested_autocorrelation():
    anom = anomalies(sample_series("T2M", 0.0, seed=2, phi=0.8))
    assert anom.autocorr(1) == pytest.approx(0.8, abs=0.06)
    assert abs(anomalies(sample_series("T2M", 0.0, seed=2)).autocorr(1)) < 0.1


def test_sample_box_average_is_not_much_quieter_than_one_point():
    bd = sample_box_data((7.5, 30.2, 11.6, 37.5))
    one = anomalies(next(iter(bd.point_data.values()))["T2M"]).std()
    avg = anomalies(bd.data["T2M"]).std()
    assert avg >= 0.8 * one  # shared regional noise: independent noise would give about one / 3


def test_sample_box_data_shape_and_opposite_rain_trends():
    bd = sample_box_data((7.5, 30.2, 11.6, 37.5))
    assert list(bd.data.columns) == ["T2M", "PRECTOTCORR", "GWETTOP"]
    assert bd.points_used == bd.points_total == len(bd.point_data) == 9
    north = analyze(bd.point_data[max(bd.point_data)]["PRECTOTCORR"], "PRECTOTCORR")
    south = analyze(bd.point_data[min(bd.point_data)]["PRECTOTCORR"], "PRECTOTCORR")
    assert north["slope_decade"] < 0 < south["slope_decade"]


# ---------------------------------------------------------------- agreement (step 7)

def _res(slope, tier):
    return {"slope_decade": slope, "tier": tier}


def test_agreement_same_direction_both_strong_agree():
    assert analyze_module.agreement(_res(0.3, "significant"), _res(0.2, "suggestive")) == "agree"
    assert analyze_module.agreement(_res(-0.3, "suggestive"), _res(-0.1, "suggestive")) == "agree"


def test_agreement_opposite_with_one_significant_disagree():
    assert analyze_module.agreement(_res(0.3, "significant"), _res(-0.2, "none")) == "disagree"


def test_agreement_weak_or_missing_is_single():
    assert analyze_module.agreement(_res(0.3, "significant"), None) == "single"
    assert analyze_module.agreement(None, _res(0.3, "significant")) == "single"
    assert analyze_module.agreement(_res(0.3, "significant"), _res(0.1, "none")) == "single"
    assert analyze_module.agreement(_res(0.3, "suggestive"), _res(-0.1, "suggestive")) == "single"


def test_agreement_on_real_analyses():
    a = analyze(sample_series("T2M", slope_decade=0.3, seed=0), "T2M")
    b = analyze(sample_series("T2M", slope_decade=0.3, seed=5), "T2M")
    c = analyze(sample_series("T2M", slope_decade=-0.3, seed=6), "T2M")
    assert analyze_module.agreement(a, b) == "agree"
    assert analyze_module.agreement(a, c) == "disagree"
