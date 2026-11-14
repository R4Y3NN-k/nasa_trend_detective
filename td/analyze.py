# SI-assisted: parts of this file were drafted with Claude (Anthropic) and reviewed by the team
"""Stats engine and verdict words. Owner: B (stats). Changes to analyze() keys need B's review.

Contract:
    anomalies(series) -> pd.Series
    analyze(series, var_id) -> dict   # keys: var_id, start, end, n_months, missing_months, span_years, mean,
        # slope_decade, ci_decade (lo, hi), p_ttest, p_mk, sen_decade, tier ("significant"|"suggestive"|"none"),
        # tests_agree, total_change, pct_decade (None unless relative), years_to_significance, short_record,
        # _anomalies, _trend_line (Series for charts)
    verdict(res) -> {"headline": str, "detail": str}
    correlate(a, b) -> {"r": float | None, "n": int}
    compare(sub_res, whole_res, sub_name, whole_name) -> str          # step 6
    agreement(res_a, res_b) -> "agree" | "disagree" | "single"        # step 7
"""
from __future__ import annotations

import pandas as pd


def anomalies(series: pd.Series) -> pd.Series:
    raise NotImplementedError("Step 2 (B)")


def analyze(series: pd.Series, var_id: str) -> dict:
    raise NotImplementedError("Step 2 (B)")


def verdict(res: dict) -> dict:
    raise NotImplementedError("Step 2 (B)")


def correlate(a: pd.Series, b: pd.Series) -> dict:
    raise NotImplementedError("Step 2 (B)")


def compare(sub_res: dict, whole_res: dict, sub_name: str, whole_name: str) -> str:
    raise NotImplementedError("Step 6 (B)")


def agreement(res_a: dict, res_b: dict | None) -> str:
    raise NotImplementedError("Step 7 (B)")
