# SI-assisted: parts of this file were drafted with Claude (Anthropic) and reviewed by the team
"""Variable catalog, regions, guided questions and shared constants. Owner: D (content).

Contract:
    VARIABLES[id] = {name, short, definition, source, power_param, units, record, relative, decimals, why,
                     caveat, fetcher ("power"|"giovanni"|"appeears"), cross_check (optional)}
    REGIONS[id]   = {name, box, type ("arid"|"savanna"|"temperate"|"polar"), blurb, parent (optional)}
                    # box = (west, south, east, north) in degrees
    QUESTIONS[id] = {label, icon, primary, linked: {region_type: var_id, "default": var_id}, why_linked: {...}}
    classify_box(box) -> region type
    linked_for(question_id, region_type) -> (var_id, why)
"""
from __future__ import annotations

FIRST_YEAR = 1981
LAST_YEAR = 2025
MIN_SPACING_DEG = 0.5
MAX_POINTS = 30

VARIABLES: dict = {}   # Step 4 (D)
REGIONS: dict = {}     # Step 4 (D)
QUESTIONS: dict = {}   # Step 4 (D)


def classify_box(box) -> str:
    raise NotImplementedError("Step 4 (D)")


def linked_for(question_id: str, region_type: str) -> tuple[str, str]:
    raise NotImplementedError("Step 4 (D)")
