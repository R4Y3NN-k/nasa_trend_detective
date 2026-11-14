# SI-assisted: parts of this file were drafted with Claude (Anthropic) and reviewed by the team
"""MODIS NDVI from finished AppEEARS area jobs. Owner: A (data). Step 8 (optional).

Contract:
    load_ndvi(task_id) -> pd.Series      # monthly, 0-1
"""
from __future__ import annotations

import pandas as pd


def load_ndvi(task_id: str) -> pd.Series:
    raise NotImplementedError("Step 8 (A)")
