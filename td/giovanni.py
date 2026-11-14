# SI-assisted: parts of this file were drafted with Claude (Anthropic) and reviewed by the team
"""Second NASA source for rain: GPM IMERG area averages via Giovanni (harmony-py). Owner: A. Step 7.

Contract:
    fetch_series_giovanni(var_id, box, start_year, end_year) -> pd.Series
"""
from __future__ import annotations

import pandas as pd


def fetch_series_giovanni(var_id: str, box, start_year: int, end_year: int) -> pd.Series:
    raise NotImplementedError("Step 7 (A)")
