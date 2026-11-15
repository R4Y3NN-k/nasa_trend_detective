# SI-assisted: parts of this file were drafted with Claude (Anthropic) and reviewed by the team
"""The map's grid maths (web/static/grid.js): ring search for the nearest land cells. Needs Node; skipped without it."""
import shutil
import subprocess
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is not installed")
def test_ring_search_tiny_sea_coastal_and_antimeridian():
    run = subprocess.run(["node", str(HERE / "grid_check.js")], capture_output=True, text=True, timeout=60)
    assert run.returncode == 0, run.stderr[-2000:]
    assert run.stdout.strip() == "ok 9"
