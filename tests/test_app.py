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
