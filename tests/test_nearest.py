# SI-assisted: parts of this file were drafted with Claude (Anthropic) and reviewed by the team
"""Ring search for the nearest land cells (tiny loops, loops on the sea, coasts, the antimeridian)."""
from td.nearest import haversine_km, nearest_land, ring


def test_ring_sizes_and_order():
    assert ring(36.0, 10.0, 0) == [(36.0, 10.0)]
    r1 = ring(36.0, 10.0, 1)
    assert len(r1) == 8 and len(ring(36.0, 10.0, 2)) == 16
    d = [haversine_km((36.0, 10.0), c) for c in r1]
    assert d == sorted(d)


def test_tiny_loop_on_land_gets_k_cells():
    cells, rings = nearest_land((36.1, 10.1), 4, lambda cs: cs)
    assert len(cells) == 4 and cells[0] == (36.0, 10.0) and rings == 1


def test_sea_only_gives_up_after_max_rings():
    calls = []
    cells, rings = nearest_land((0.0, -30.0), 4, lambda cs: calls.append(len(cs)) or [], max_rings=3)
    assert cells == [] and rings == 3 and calls == [1, 8, 16, 24]


def test_coast_takes_the_land_side_only():
    land = lambda cs: [c for c in cs if c[1] >= 10.0]          # sea to the west of 10 E  # noqa: E731
    cells, _ = nearest_land((36.0, 9.4), 4, land)
    assert len(cells) == 4 and all(lon >= 10.0 for _, lon in cells)


def test_have_counts_and_is_not_returned():
    cells, _ = nearest_land((36.0, 10.0), 4, lambda cs: cs, have=[(36.0, 10.0), (36.5, 10.0)])
    assert len(cells) == 2 and (36.0, 10.0) not in cells and (36.5, 10.0) not in cells


def test_antimeridian_wraps():
    r1 = ring(0.0, 179.9, 1)
    lons = {lon for _, lon in r1}
    assert -180.0 in lons and 179.375 in lons and all(-180 <= lon < 180 for lon in lons)
    cells, _ = nearest_land((0.0, 179.9), 4, lambda cs: cs)
    assert len(cells) == 4


def test_pole_is_clamped():
    assert all(abs(lat) <= 90 for lat, _ in ring(89.9, 0.0, 2))
