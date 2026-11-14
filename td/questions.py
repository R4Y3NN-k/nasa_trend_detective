# SI-assisted: parts of this file were drafted with Claude (Anthropic) and reviewed by the team
"""Which questions fit this place? Climate type from the area's own NASA POWER averages, then a ranked list.

No lat/lon boxes: a cold, snowy area is recognised as such whether it is in Canada, the Alps or Siberia, and a
desert whether it is in Arabia or Australia. The ranking depends only on the climate (what people there ask
about), never on which trend looks strongest, so it does not bias the tests.

Contract:
    climate_type(means: dict[var_id, float]) -> {"type", "label", "reason"}
    relevant_questions(means) -> [question_id, ...]   # ranked for that climate, only questions with data there
"""
from __future__ import annotations

# id -> label, primary variable, linked variable (shown as supporting evidence) and why they are linked.
CATALOG = {
    "hotter": {"label": "Is it getting hotter?", "primary": "T2M", "linked": "PRECTOTCORR",
               "why": "Warmer air can change how much rain falls."},
    "heat": {"label": "Are the hottest days getting hotter?", "primary": "T2M_MAX", "linked": "GWETTOP",
             "why": "Dry soil lets the ground heat up more on hot days."},
    "milder": {"label": "Are the coldest nights getting milder?", "primary": "T2M_MIN", "linked": "SNODP",
               "why": "Snow cover keeps nights cold, so the two often change together."},
    "frost": {"label": "Are there fewer frost days?", "primary": "FROST_DAYS", "linked": "T2M_MIN",
              "why": "Frost days follow how cold the coldest nights get."},
    "snow": {"label": "Is it snowing less?", "primary": "PRECSNOLAND", "linked": "T2M",
             "why": "In warmer winters more of the precipitation falls as rain instead of snow."},
    "snowcover": {"label": "Is the snow cover getting thinner?", "primary": "SNODP", "linked": "T2M",
                  "why": "Warmer months melt snow sooner."},
    "rain": {"label": "Is rainfall changing?", "primary": "PRECTOTCORR", "linked": "GWETTOP",
             "why": "Rain is what refills the soil, so the two should move together."},
    "drying": {"label": "Is the land drying out?", "primary": "GWETTOP", "linked": "T2M",
               "why": "Rising heat is a common reason soils dry."},
    "humid": {"label": "Is the air getting more humid?", "primary": "RH2M", "linked": "T2M",
              "why": "Air temperature changes how much moisture the air holds."},
}

# What people in each climate most need to know, most important first.
RELEVANCE = {
    "cold": ["snowcover", "snow", "milder", "frost", "hotter", "rain"],
    "arid": ["heat", "hotter", "drying", "rain", "humid"],
    "semi_arid": ["hotter", "heat", "drying", "rain", "humid"],
    "tropical": ["rain", "heat", "humid", "drying", "hotter"],
    "temperate": ["hotter", "rain", "heat", "frost", "snow", "drying", "milder"],
}
DEFAULT = ["hotter", "rain", "drying"]   # before the area's data has loaded

LABELS = {
    "cold": "Cold, snowy climate",
    "arid": "Desert climate",
    "semi_arid": "Warm, dry climate",
    "tropical": "Hot, humid climate",
    "temperate": "Temperate climate",
}

# A question is only offered where its variable actually happens (no snow questions in a desert).
MIN_MEAN = {"SNODP": 0.5, "PRECSNOLAND": 0.02, "FROST_DAYS": 1.0}


def _get(means, key, default=None):
    v = means.get(key)
    return default if v is None else float(v)


def climate_type(means: dict) -> dict:
    """Simple, explainable rules on the long-term averages (rain in mm/day: 1.0 is about 365 mm a year)."""
    t, rain, snow = _get(means, "T2M", 15.0), _get(means, "PRECTOTCORR", 2.0), _get(means, "SNODP", 0.0)
    if t < 5 or snow >= 2:
        kind = "cold"
        reason = f"average {t:.1f} °C, {snow:.1f} cm of snow on the ground on average"
    elif rain < 1.0:
        kind = "arid"
        reason = f"only about {rain * 365:.0f} mm of rain a year, average {t:.1f} °C"
    elif rain < 1.5 and t >= 15:
        kind = "semi_arid"
        reason = f"about {rain * 365:.0f} mm of rain a year, average {t:.1f} °C"
    elif t >= 22 and rain >= 2.5:
        kind = "tropical"
        reason = f"average {t:.1f} °C, about {rain * 365:.0f} mm of rain a year"
    else:
        kind = "temperate"
        reason = f"average {t:.1f} °C, about {rain * 365:.0f} mm of rain a year"
    return {"type": kind, "label": LABELS[kind], "reason": reason}


def relevant_questions(means: dict | None) -> list[str]:
    if not means:
        return list(DEFAULT)
    keep = []
    for qid in RELEVANCE[climate_type(means)["type"]]:
        var = CATALOG[qid]["primary"]
        if var not in means or (var in MIN_MEAN and _get(means, var, 0.0) < MIN_MEAN[var]):
            continue
        keep.append(qid)
    return keep
