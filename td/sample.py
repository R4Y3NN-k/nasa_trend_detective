# SI-assisted: parts of this file were drafted with Claude (Anthropic) and reviewed by the team
"""Synthetic data so C and D can build before real data exists. Owner: B (stats).

Contract:
    sample_series(var_id="T2M", slope_decade=0.3, years=45, seed=0) -> pd.Series
    sample_box_data(box) -> BoxData
"""
from __future__ import annotations

import pandas as pd

from td.fetch import BoxData


def sample_series(var_id: str = "T2M", slope_decade: float = 0.3, years: int = 45, seed: int = 0) -> pd.Series:
    raise NotImplementedError("Step 2 (B), by 18:00")


def sample_box_data(box) -> BoxData:
    raise NotImplementedError("Step 2 (B), by 18:00")
