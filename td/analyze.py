"""Stats engine: monthly series -> trend per decade, two significance tests, verdict tier and plain words.

Method: monthly anomalies; OLS with Newey-West (HAC, 12 lags) errors for the slope, 95% CI and t-test;
Hamed-Rao modified Mann-Kendall for autocorrelated data; Sen's slope on decimal years.

SI-assisted: parts of this file were drafted with Claude (Anthropic) and reviewed by the team
"""
import numpy as np
import pandas as pd
import pymannkendall as mk
import statsmodels.api as sm
from scipy import stats

MIN_MONTHS = 60  # each calendar-month mean needs several years for the anomalies to mean anything
SHORT_RECORD_YEARS = 30

# Used only until td/config.py (owner D) defines VARIABLES.
_FALLBACK_VARIABLES = {
    "T2M": {"name": "Air temperature", "units": "°C", "relative": False, "decimals": 2},
    "PRECTOTCORR": {"name": "Rain and snow", "units": "mm/day", "relative": True, "decimals": 2},
    "GWETTOP": {"name": "Topsoil wetness", "units": "(0 to 1)", "relative": True, "decimals": 3},
    "T2M_MAX": {"name": "Hottest temperature of the month", "units": "°C", "relative": False, "decimals": 2},
    "T2M_MIN": {"name": "Coldest temperature of the month", "units": "°C", "relative": False, "decimals": 2},
    "FROST_DAYS": {"name": "Frost days", "units": "days/month", "relative": True, "decimals": 2},
    "PRECSNOLAND": {"name": "Snowfall", "units": "mm/day", "relative": True, "decimals": 3},
    "SNODP": {"name": "Snow depth", "units": "cm", "relative": True, "decimals": 2},
    "RH2M": {"name": "Relative humidity", "units": "%", "relative": False, "decimals": 2},
    "EVLAND": {"name": "Evaporation from the land", "units": "mm/day", "relative": True, "decimals": 3},
    "GWETROOT": {"name": "Root-zone soil wetness", "units": "(0 to 1)", "relative": True, "decimals": 3},
}


def _var_info(var_id):
    try:
        from td.config import VARIABLES
    except ImportError:
        VARIABLES = {}
    info = VARIABLES.get(var_id) or _FALLBACK_VARIABLES.get(var_id) or {}
    return {
        "name": info.get("name", var_id),
        "units": info.get("units", ""),
        "relative": bool(info.get("relative", False)),
        "decimals": int(info.get("decimals", 2)),
    }


def anomalies(series) -> pd.Series:
    """Each value minus the mean of its calendar month over the whole record (removes the seasons)."""
    s = series.astype(float)
    return s - s.groupby(s.index.month).transform("mean")


def _decimal_years(index):
    return index.year + (index.month - 1) / 12.0


def analyze(series, var_id) -> dict:
    s = series.astype(float).sort_index()
    valid = s.dropna()
    if len(valid) < MIN_MONTHS:
        raise ValueError(f"Need at least {MIN_MONTHS} months of data, got {len(valid)}.")

    full_range = pd.date_range(valid.index[0], valid.index[-1], freq="MS")
    s = s.reindex(full_range)
    missing = int(s.isna().sum())
    span_years = len(full_range) / 12.0

    anom = anomalies(s).dropna()
    x = np.asarray(_decimal_years(anom.index), dtype=float)
    y = anom.to_numpy()

    fit = sm.OLS(y, sm.add_constant(x)).fit(cov_type="HAC", cov_kwds={"maxlags": 12})
    slope_decade = float(fit.params[1]) * 10
    ci_lo, ci_hi = (float(v) * 10 for v in fit.conf_int(alpha=0.05)[1])
    p_ttest = float(fit.pvalues[1])
    t_stat = float(fit.tvalues[1])

    with np.errstate(invalid="ignore"):
        p_mk = float(mk.hamed_rao_modification_test(y).p)
    # Hamed-Rao's variance correction can turn negative (NaN p), typically on strongly autocorrelated series.
    # Fallback: pre-whitening. Checked on flat AR(1) phi=0.8 series where Hamed-Rao fails: the original,
    # Yue-Wang and trend-free pre-whitening tests all gave p = 0.0000 (false alarms); pre-whitening did not.
    mk_fallback = not np.isfinite(p_mk)
    if mk_fallback:
        p_mk = float(mk.pre_whitening_modification_test(y).p)
    sen_decade = float(stats.theilslopes(y, x)[0]) * 10

    tests_agree = bool(np.sign(slope_decade) == np.sign(sen_decade) and slope_decade != 0)
    if p_ttest < 0.05 and p_mk < 0.05 and tests_agree:
        tier = "significant"
    elif p_ttest < 0.10 or p_mk < 0.10:
        tier = "suggestive"
    else:
        tier = "none"

    info = _var_info(var_id)
    mean = float(valid.mean())
    pct_decade = slope_decade / mean * 100 if info["relative"] and mean > 0 else None

    n = len(y)
    if tier == "significant":
        years_to_significance = 0.0
    elif t_stat == 0:
        years_to_significance = None
    else:
        # The slope's t grows like n^1.5, so |t| reaches 1.96 at n * (1.96/|t|)^(2/3) months if the trend holds.
        n_needed = n * (1.96 / abs(t_stat)) ** (2 / 3)
        years_to_significance = max(0.0, (n_needed - n) / 12.0)

    trend_line = pd.Series(fit.params[0] + fit.params[1] * x, index=anom.index)

    return {
        "var_id": var_id,
        "start": valid.index[0].strftime("%Y-%m"),
        "end": valid.index[-1].strftime("%Y-%m"),
        "n_months": n,
        "missing_months": missing,
        "span_years": span_years,
        "mean": mean,
        "slope_decade": slope_decade,
        "ci_decade": (ci_lo, ci_hi),
        "p_ttest": p_ttest,
        "p_mk": p_mk,
        "mk_fallback": mk_fallback,
        "sen_decade": sen_decade,
        "tier": tier,
        "tests_agree": tests_agree,
        "total_change": slope_decade * span_years / 10,
        "pct_decade": pct_decade,
        "years_to_significance": years_to_significance,
        "short_record": span_years < SHORT_RECORD_YEARS,
        "_anomalies": anom,
        "_trend_line": trend_line,
    }


def verdict(res) -> dict:
    info = _var_info(res["var_id"])
    name, units, dec = info["name"], info["units"], info["decimals"]
    slope = res["slope_decade"]
    direction = "rising" if slope > 0 else "falling"
    amount = f"{abs(slope):.{dec}f} {units}".strip()
    pct = f" ({abs(res['pct_decade']):.1f}% of the average)" if res["pct_decade"] is not None else ""
    lo, hi = res["ci_decade"]
    record = f"{res['start']} to {res['end']} ({res['span_years']:.0f} years, {res['missing_months']} months missing)"
    tests = f"t-test p = {res['p_ttest']:.3f}, Mann-Kendall p = {res['p_mk']:.3f}"

    if res["tier"] == "significant":
        headline = f"{name} {direction} about {amount} per decade"
        detail = (
            f"Both tests agree the trend is unlikely to be chance ({tests}). "
            f"95% confidence interval: {lo:.{dec}f} to {hi:.{dec}f} {units} per decade{pct}. "
            f"Record: {record}. This shows a change, not its cause."
        )
    elif res["tier"] == "suggestive":
        headline = f"{name} possibly {direction}"
        detail = (
            f"The data lean towards a {direction} trend of about {amount} per decade{pct}, "
            f"but the tests are not strong enough to be sure ({tests}). Record: {record}."
        )
    else:
        headline = "No clear trend yet"
        detail = f"{name}: the change over {record} is within what natural ups and downs could produce ({tests})."

    yts = res["years_to_significance"]
    if res["tier"] != "significant" and yts is not None and yts <= 50:
        detail += f" If the current rate continued, it would take about {yts:.0f} more years of data to be sure."
    if res["short_record"]:
        detail += " The record is shorter than 30 years, so treat this with extra caution."
    if res.get("mk_fallback"):
        detail += (" Note: the usual autocorrelation correction of the Mann-Kendall test could not be computed for"
                   " this series, so its pre-whitened version was used instead.")
    return {"headline": headline, "detail": detail}


def correlate(a, b) -> dict:
    """Pearson r between the monthly anomalies of two series, over the months both have."""
    both = pd.concat([anomalies(a), anomalies(b)], axis=1, join="inner").dropna()
    n = len(both)
    if n < 3 or both.iloc[:, 0].std() == 0 or both.iloc[:, 1].std() == 0:
        return {"r": None, "n": n}
    return {"r": float(both.iloc[:, 0].corr(both.iloc[:, 1])), "n": n}


def compare(sub_res, whole_res, sub_name, whole_name) -> str:
    """One plain sentence comparing two trends of the same variable (a part vs the whole, or highland vs lowland).

    "Faster" or "slower" only when the two 95% intervals do not overlap; otherwise the rates are called similar,
    because the difference could be chance.
    """
    info = _var_info(sub_res["var_id"])
    dec, units = info["decimals"], info["units"]
    a, b = sub_res["slope_decade"], whole_res["slope_decade"]
    rate = lambda x: f"{x:+.{dec}f} {units}".strip()  # noqa: E731
    lo_a, hi_a = sub_res["ci_decade"]
    lo_b, hi_b = whole_res["ci_decade"]
    both = f"({rate(a)} vs {rate(b)} per decade)"
    if hi_a < lo_b or hi_b < lo_a:
        if np.sign(a) != np.sign(b) and a != 0 and b != 0:
            return (f"{sub_name} and {whole_name} change in opposite directions {both}; "
                    "the difference is larger than chance would explain.")
        word = "faster" if abs(a) > abs(b) else "slower"
        return f"{sub_name} changes {word} than {whole_name} {both}; the difference is larger than chance would explain."
    return (f"{sub_name} and {whole_name} change at a similar rate {both}; "
            "the difference is within the uncertainty.")


def agreement(res_a, res_b) -> str:
    """Two independent datasets, same variable: do they tell the same story?

    agree    = same direction and both at least suggestive
    disagree = opposite directions and at least one of them significant
    single   = only one source, or the evidence is too weak to say either way
    """
    if res_a is None or res_b is None:
        return "single"
    sa, sb = np.sign(res_a["slope_decade"]), np.sign(res_b["slope_decade"])
    strong = ("significant", "suggestive")
    if sa != 0 and sa == sb and res_a["tier"] in strong and res_b["tier"] in strong:
        return "agree"
    if sa != 0 and sb != 0 and sa != sb and "significant" in (res_a["tier"], res_b["tier"]):
        return "disagree"
    return "single"
