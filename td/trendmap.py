# SI-assisted: parts of this file were drafted with Claude (Anthropic) and reviewed by the team
"""Per-point trends with Benjamini-Hochberg FDR: the opposite-trends zone map. Owner: B. Step 5.

Contract:
    trend_grid(point_data, var_id, fdr_alpha=0.10) -> pd.DataFrame
        # columns: lat, lon, slope_decade, pct_decade, p_ttest, p_mk, q_fdr, significant
"""
from __future__ import annotations

import pandas as pd


def trend_grid(point_data: dict, var_id: str, fdr_alpha: float = 0.10) -> pd.DataFrame:
    raise NotImplementedError("Step 5 (B)")
