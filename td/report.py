# SI-assisted: parts of this file were drafted with Claude (Anthropic) and reviewed by the team
"""Case report (Markdown) and CSV download. Owner: D (content).

Contract:
    markdown_report(case, res, words, linked=None) -> str
    csv_bytes(series, res) -> bytes
"""
from __future__ import annotations

import pandas as pd


def markdown_report(case: dict, res: dict, words: dict, linked: dict | None = None) -> str:
    raise NotImplementedError("Step 4 (D)")


def csv_bytes(series: pd.Series, res: dict) -> bytes:
    raise NotImplementedError("Step 4 (D)")
