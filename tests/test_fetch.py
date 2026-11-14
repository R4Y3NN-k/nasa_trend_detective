# SI-assisted: parts of this file were drafted with Claude (Anthropic) and reviewed by the team
"""Data layer tests (A adds the real ones in step 1). Offline: no network."""
from td import cache, fetch


def test_data_contracts_exist():
    for name in ("make_key", "get", "put"):
        assert callable(getattr(cache, name))
    for name in ("fetch_box", "grid_points", "BoxData", "FetchError"):
        assert hasattr(fetch, name)
    assert set(fetch.BoxData.__dataclass_fields__) == {"data", "points_total", "points_used", "points", "point_data"}
