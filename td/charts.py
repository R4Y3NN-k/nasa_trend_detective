# SI-assisted: parts of this file were drafted with Claude (Anthropic) and reviewed by the team
"""Plotly figures. Owner: C (dashboard).

Contract:
    trend_figure(series, res, view="anomaly"|"raw") -> go.Figure
    trend_map_figure(grid_df, var_id) -> go.Figure                    # step 5
    box_figure(points, box) -> go.Figure
"""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go


def trend_figure(series: pd.Series, res: dict, view: str = "anomaly") -> go.Figure:
    raise NotImplementedError("Step 3 (C)")


def trend_map_figure(grid_df: pd.DataFrame, var_id: str) -> go.Figure:
    raise NotImplementedError("Step 5 (C)")


def box_figure(points: list, box) -> go.Figure:
    raise NotImplementedError("Step 3 (C)")
