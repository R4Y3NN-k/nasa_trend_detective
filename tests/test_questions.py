# SI-assisted: parts of this file were drafted with Claude (Anthropic) and reviewed by the team
"""Region-aware questions: climate from real NASA POWER long-term means (1981-2025, fetched Nov 2026)."""
from td.questions import CATALOG, climate_type, relevant_questions

WINNIPEG = {"T2M": 3.29, "PRECTOTCORR": 1.48, "GWETTOP": 0.55, "T2M_MAX": 18.7, "T2M_MIN": -11.8,
            "FROST_DAYS": 15.4, "PRECSNOLAND": 0.33, "SNODP": 9.36, "RH2M": 76.3}
RIYADH = {"T2M": 25.6, "PRECTOTCORR": 0.13, "GWETTOP": 0.12, "T2M_MAX": 38.2, "T2M_MIN": 14.1,
          "FROST_DAYS": 0.05, "PRECSNOLAND": 0.00002, "SNODP": 0.0008, "RH2M": 25.4}
TUNIS = {"T2M": 18.5, "PRECTOTCORR": 1.31, "GWETTOP": 0.48, "T2M_MAX": 32.3, "T2M_MIN": 8.74,
         "FROST_DAYS": 0.03, "PRECSNOLAND": 0.0004, "SNODP": 0.015, "RH2M": 65.8}


def test_canada_gets_snow_and_cold_questions_first():
    assert climate_type(WINNIPEG)["type"] == "cold"
    qs = relevant_questions(WINNIPEG)
    assert qs[:4] == ["snowcover", "snow", "milder", "frost"]


def test_desert_gets_heat_and_drying_and_no_snow():
    assert climate_type(RIYADH)["type"] == "arid"
    qs = relevant_questions(RIYADH)
    assert qs[0] == "heat" and "drying" in qs[:3]
    assert not {"snow", "snowcover", "frost", "milder"} & set(qs)


def test_tunis_is_warm_and_dry():
    assert climate_type(TUNIS)["type"] == "semi_arid"
    assert relevant_questions(TUNIS)[0] == "hotter"


def test_before_data_default_and_every_question_valid():
    assert relevant_questions(None) == ["hotter", "rain", "drying"]
    for q in CATALOG.values():
        assert q["primary"] != q["linked"]


def test_climate_endpoint_from_means_is_instant_and_validated():
    import pytest

    from td.fetch import FetchError
    from web import server

    out = server.climate_from_means({"means": WINNIPEG})
    assert out["climate"]["type"] == "cold" and out["questions"][0]["id"] == "snowcover"
    out = server.climate_from_means({"means": {**RIYADH, "EVIL": "x", "RH2M": float("nan")}})
    assert out["climate"]["type"] == "arid"
    with pytest.raises(FetchError):
        server.climate_from_means({"means": {"PRECTOTCORR": 1.0}})


def test_evaporation_and_root_zone_questions_only_where_they_happen():
    from td.questions import relevant_questions
    tunis = relevant_questions({**TUNIS, "EVLAND": 0.9, "GWETROOT": 0.45})
    assert "evaporation" in tunis and "rootzone" in tunis
    assert tunis.index("drying") < tunis.index("rootzone")          # topsoil first, deeper soil after
    riyadh = relevant_questions({**RIYADH, "EVLAND": 0.03, "GWETROOT": 0.1})
    assert "evaporation" not in riyadh and "rootzone" in riyadh     # almost nothing evaporates in a desert
