# SI-assisted: parts of this file were drafted with Claude (Anthropic) and reviewed by the team
"""App click-through without network (B and C extend this in step 3)."""
from pathlib import Path

from streamlit.testing.v1 import AppTest

from td import config

APP = str(Path(__file__).resolve().parent.parent / "app.py")


def test_config_constants():
    assert (config.FIRST_YEAR, config.LAST_YEAR) == (1981, 2025)
    assert config.MAX_POINTS == 30 and config.MIN_SPACING_DEG == 0.5


def test_app_starts_without_errors():
    at = AppTest.from_file(APP, default_timeout=60).run()
    assert not at.exception


def test_trend_zones_tree_drives_the_map(monkeypatch):
    monkeypatch.setenv("TD_SAMPLE", "1")
    at = AppTest.from_file(APP, default_timeout=180)
    at.session_state["step"] = 3
    at.run()
    assert not at.exception
    assert at.selectbox(key="zone").value == "all"
    assert len(at.get("plotly_chart")) >= 3  # time series, zone tree, zone map

    at.selectbox(key="zone").set_value("all/A").run()
    assert not at.exception
    assert any(m.value.startswith("**Zone A ·") for m in at.markdown)

    at.multiselect(key="cluster_vars").set_value(["T2M", "PRECTOTCORR"]).run()
    assert not at.exception
    assert at.selectbox(key="zone").value == "all/A"  # every tree has a Zone A, so the choice is kept
    assert any(o.strip().startswith("Zone A (") for o in at.selectbox(key="zone").options)
