# SI-assisted: parts of this file were drafted with Claude (Anthropic) and reviewed by the team
"""NASA POWER client: grid of points, land mask, cos(latitude)-weighted average. Owner: A (data).

Contract:
    fetch_box(box, start_year, end_year) -> BoxData     # box = (west, south, east, north)
    grid_points(box) -> list[tuple[float, float]]       # (lat, lon) cell centres
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass
class BoxData:
    data: pd.DataFrame        # index: month start (DatetimeIndex); columns: variable ids ("T2M", ...)
    points_total: int         # grid points requested
    points_used: int          # land points averaged
    points: list              # [(lat, lon, is_land)]
    point_data: dict          # {(lat, lon): DataFrame like .data}, land points only


class FetchError(RuntimeError):
    """Raised when a box cannot be fetched. The message is safe to show users."""


def grid_points(box) -> list[tuple[float, float]]:
    raise NotImplementedError("Step 1 (A)")


def fetch_box(box, start_year: int, end_year: int) -> BoxData:
    raise NotImplementedError("Step 1 (A)")
