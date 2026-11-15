# SI-assisted: parts of this file were drafted with Claude (Anthropic) and reviewed by the team
"""Zone map (step 5) and trend-zone tree. Offline, synthetic data only."""
import numpy as np
import pandas as pd
import pytest

from td import config
from td.sample import sample_box_data, sample_series
from td.trendmap import GRID_COLUMNS, ROOT, cluster_tree, place_name, position_word, trend_grid

BOX = (7.5, 30.2, 11.6, 37.5)


def two_group_points():
    """12 points: the two northern rows warm (+0.6 °C/decade), the two southern rows cool (-0.6)."""
    data = {}
    for r, lat in enumerate((30.0, 31.0, 32.0, 33.0)):
        for c, lon in enumerate((9.0, 10.0, 11.0)):
            seed = 10 * r + c
            data[(lat, lon)] = pd.DataFrame({
                "T2M": sample_series("T2M", 0.6 if lat >= 32 else -0.6, seed=seed),
                "PRECTOTCORR": sample_series("PRECTOTCORR", 0.0, seed=500 + seed),
            })
    return data


def grids_for(point_data, var_ids):
    return {v: trend_grid(point_data, v) for v in var_ids}


def check_tree_integrity(tree, n_points):
    ids = set(tree["id"])
    assert len(ids) == len(tree)
    root = tree[tree["id"] == ROOT].iloc[0]
    assert root["parent"] == "" and root["n_points"] == n_points
    for _, node in tree[tree["id"] != ROOT].iterrows():
        assert node["parent"] in ids
    for node_id, children in tree[tree["id"] != ROOT].groupby("parent"):
        parent = tree.set_index("id").loc[node_id]
        assert children["n_points"].sum() == parent["n_points"]
        assert sorted(sum(children["members"], [])) == sorted(parent["members"])
    leaves = tree[~tree["id"].isin(tree["parent"])]
    assert len(leaves) == n_points and (leaves["n_points"] == 1).all()


# ---------------------------------------------------------------- trend_grid (step 5)

def test_trend_grid_columns_and_opposite_rain_trends():
    bd = sample_box_data(BOX)
    grid = trend_grid(bd.point_data, "PRECTOTCORR")
    assert list(grid.columns) == GRID_COLUMNS and len(grid) == 9
    north = grid[grid["lat"] == grid["lat"].max()]
    south = grid[grid["lat"] == grid["lat"].min()]
    assert (north["slope_decade"] < 0).all()
    assert south["slope_decade"].mean() > north["slope_decade"].mean()
    assert (grid["q_fdr"] >= grid[["p_ttest", "p_mk"]].max(axis=1) - 1e-12).all()


def test_flat_points_are_rarely_significant_after_fdr():
    point_data = {(30.0 + i, 10.0): pd.DataFrame({"T2M": sample_series("T2M", 0.0, seed=100 + i)}) for i in range(20)}
    assert trend_grid(point_data, "T2M")["significant"].sum() <= 2


def test_trend_grid_empty_and_missing_variable():
    assert list(trend_grid({}, "T2M").columns) == GRID_COLUMNS
    assert trend_grid({(0.0, 0.0): pd.DataFrame({"T2M": sample_series()})}, "GWETTOP").empty


# ---------------------------------------------------------------- cluster_tree

def test_tree_separates_two_clearly_different_groups():
    point_data = two_group_points()
    tree = cluster_tree(grids_for(point_data, ["T2M"]), features=["T2M"])
    check_tree_integrity(tree, 12)
    zones = tree[tree["parent"] == ROOT].set_index("label")
    assert list(zones.index) == ["Zone A", "Zone B"]  # north first
    assert all(lat >= 32 for lat, _ in zones.loc["Zone A", "members"]) and zones.loc["Zone A", "value"] > 0
    assert all(lat <= 31 for lat, _ in zones.loc["Zone B", "members"]) and zones.loc["Zone B", "value"] < 0
    assert zones.loc["Zone A", "position"] == "north" and zones.loc["Zone B", "position"] == "south"
    assert zones.loc["Zone A", "n_significant"] == 6


def test_tree_on_sample_box_holds_together():
    bd = sample_box_data(BOX)
    tree = cluster_tree(grids_for(bd.point_data, ["PRECTOTCORR", "T2M"]), features=["PRECTOTCORR", "T2M"])
    check_tree_integrity(tree, 9)
    assert tree["depth"].max() <= 3


def test_zones_by_one_variable_coloured_by_another():
    point_data = two_group_points()
    grids = grids_for(point_data, ["T2M", "PRECTOTCORR"])
    tree = cluster_tree(grids, features=["T2M"], color_var="PRECTOTCORR")
    rain = grids["PRECTOTCORR"].set_index(["lat", "lon"])["pct_decade"]
    for _, node in tree.iterrows():
        assert node["value"] == pytest.approx(np.mean([rain.loc[m] for m in node["members"]]))
    zones = tree[tree["parent"] == ROOT]
    assert {frozenset(lat >= 32 for lat, _ in m) for m in zones["members"]} == {frozenset({True}), frozenset({False})}
    assert "Rain and snow" in tree.iloc[0]["sentence"] and "Air temperature" in tree.iloc[0]["sentence"]


def test_too_few_points_gives_root_and_leaves_only():
    point_data = {k: v for k, v in list(two_group_points().items())[:3]}
    tree = cluster_tree(grids_for(point_data, ["T2M"]))
    assert set(tree["depth"]) == {0, 1} and len(tree) == 4


def test_sentences():
    tree = cluster_tree(grids_for(two_group_points(), ["T2M"]))
    assert "average of point trends" in tree.iloc[0]["sentence"]
    zone = tree[tree["label"] == "Zone A"].iloc[0]["sentence"]
    assert zone.startswith("Zone A · north · Air temperature +0.") and "6 points (6 significant)" in zone
    leaf = tree[tree["n_points"] == 1].iloc[0]
    lat, lon = leaf["members"][0]
    assert leaf["sentence"].startswith(f"{lat:.2f}°N {lon:.2f}°E · Air temperature")
    assert f"{lat:.2f}°, " not in leaf["sentence"]  # coordinates once, not twice


def test_place_name_prefers_the_smallest_governorate(monkeypatch):
    monkeypatch.setattr(config, "REGIONS", {
        "tunisia": {"name": "Tunisia", "box": (7.5, 30.2, 11.6, 37.5)},
        "north": {"name": "Northern Tunisia", "box": (8.0, 34.5, 11.2, 37.5), "parent": "tunisia"},
        "tunis": {"name": "Tunis", "box": (9.8, 36.5, 10.6, 37.1), "parent": "tunisia"},
    })
    assert place_name(36.8, 10.2) == "Tunis"
    assert place_name(35.0, 9.0) == "Northern Tunisia"
    assert place_name(31.0, 9.0) == "31.00°N 9.00°E"  # parentless presets are not used as names
    assert place_name(-8.8, -13.2) == "8.80°S 13.20°W"

    tree = cluster_tree({"T2M": trend_grid({(36.8, 10.2): pd.DataFrame({"T2M": sample_series()})}, "T2M")})
    leaf = tree[tree["parent"] == ROOT].iloc[0]
    assert leaf["label"] == "Tunis" and "36.80°, 10.20°" in leaf["sentence"]


def test_position_word():
    pts = [(lat, lon) for lat in (30, 31, 32, 33) for lon in (8, 9, 10, 11)]
    assert position_word([(33, 8), (32, 8)], pts) == "north-west"
    assert position_word([(30, 11)], pts) == "south-east"
    assert position_word([(31, 9), (32, 10)], pts) == "centre"
