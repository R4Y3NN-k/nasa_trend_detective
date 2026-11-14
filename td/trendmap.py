# SI-assisted: parts of this file were drafted with Claude (Anthropic) and reviewed by the team
"""Per-point trends with Benjamini-Hochberg FDR (the opposite-trends zone map) and trend zones. Owner: B.

Contract:
    trend_grid(point_data, var_id, fdr_alpha=0.10) -> pd.DataFrame
        # columns: lat, lon, slope_decade, pct_decade, p_ttest, p_mk, q_fdr, significant
    cluster_tree(grids, features=None, color_var=None) -> pd.DataFrame
        # one row per node of the zone tree: id, parent, label, depth, n_points, value, n_significant,
        # members, position, sentence, mean_<var> per feature

Zones are descriptive: points grouped because their trends look alike. They are not a statistical test;
significance comes from trend_grid (FDR across points, Wilks 2016).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.cluster.hierarchy import cut_tree, linkage
from statsmodels.stats.multitest import multipletests

from td.analyze import _var_info, analyze

GRID_COLUMNS = ["lat", "lon", "slope_decade", "pct_decade", "p_ttest", "p_mk", "q_fdr", "significant"]
CLUSTER_LEVELS = (2, 4)      # zones, then sub-zones; single points are the leaves
MIN_POINTS_TO_CLUSTER = 4
ROOT = "all"


# ---------------------------------------------------------------- step 5: per-point trends + FDR

def trend_grid(point_data: dict, var_id: str, fdr_alpha: float = 0.10) -> pd.DataFrame:
    """analyze() at every land point; significant = FDR q < alpha and both tests agree in sign.

    The FDR uses the larger of the two p-values per point, so a point counts only if both tests pass.
    """
    rows = []
    for (lat, lon), frame in point_data.items():
        if var_id not in frame:
            continue
        try:
            res = analyze(frame[var_id], var_id)
        except ValueError:
            continue
        rows.append({"lat": lat, "lon": lon, "slope_decade": res["slope_decade"], "pct_decade": res["pct_decade"],
                     "p_ttest": res["p_ttest"], "p_mk": res["p_mk"], "tests_agree": res["tests_agree"]})
    if not rows:
        return pd.DataFrame(columns=GRID_COLUMNS)

    df = pd.DataFrame(rows)
    p_both = np.maximum(df["p_ttest"], df["p_mk"])
    df["q_fdr"] = multipletests(p_both, alpha=fdr_alpha, method="fdr_bh")[1]
    df["significant"] = (df["q_fdr"] < fdr_alpha) & df["tests_agree"].astype(bool)
    return df[GRID_COLUMNS].reset_index(drop=True)


def trend_value(grid: pd.DataFrame) -> tuple[pd.Series, bool]:
    """The number to show per point: % per decade when every point has one (relative variables), else the slope.

    Same rule as the zone map, so the tree and the map share one colour scale.
    """
    use_pct = len(grid) > 0 and grid["pct_decade"].notna().all()
    return (grid["pct_decade"] if use_pct else grid["slope_decade"]).astype(float), bool(use_pct)


# ---------------------------------------------------------------- trend zones (cluster tree)

def place_name(lat: float, lon: float) -> str:
    """Smallest preset with a parent (a governorate or sub-region) that contains the point, else coordinates."""
    try:
        from td.config import REGIONS
    except ImportError:
        REGIONS = {}
    best, best_area = None, None
    for region in REGIONS.values():
        if "parent" not in region:
            continue
        west, south, east, north = region["box"]
        if west <= lon <= east and south <= lat <= north:
            area = (east - west) * (north - south)
            if best_area is None or area < best_area:
                best, best_area = region["name"], area
    if best:
        return best
    return f"{abs(lat):.2f}°{'N' if lat >= 0 else 'S'} {abs(lon):.2f}°{'E' if lon >= 0 else 'W'}"


def position_word(members, all_points) -> str:
    """'north', 'south-east', 'centre', ... for a group of points relative to all points."""
    lats = np.array([p[0] for p in all_points])
    lons = np.array([p[1] for p in all_points])
    zlat = (np.mean([p[0] for p in members]) - lats.mean()) / (lats.std() or 1.0)
    zlon = (np.mean([p[1] for p in members]) - lons.mean()) / (lons.std() or 1.0)
    ns = ("north" if zlat > 0 else "south") if abs(zlat) >= 0.35 else ""
    ew = ("east" if zlon > 0 else "west") if abs(zlon) >= 0.35 else ""
    return "-".join(w for w in (ns, ew) if w) or "centre"


def format_trend(value: float, var_id: str, pct: bool) -> str:
    if pct:
        return f"{value:+.1f}% per decade"
    info = _var_info(var_id)
    return " ".join(p for p in (f"{value:+.{info['decimals']}f}", info["units"], "per decade") if p)


def cluster_tree(grids: dict, features=None, color_var=None) -> pd.DataFrame:
    """Nested trend zones: all points -> zones -> sub-zones -> single points.

    grids: {var_id: trend_grid(...)}. features: the variables whose trends define the zones (default: all).
    color_var: the variable whose trend colours each node (default: the first feature); it should be the
    variable shown on the map. Points are clustered with Ward linkage on their trends, each variable scaled
    to unit spread across points, and the tree is cut at CLUSTER_LEVELS (nested cuts of one linkage).
    """
    features = list(features or grids)
    color_var = color_var or features[0]
    shown = [color_var] + [v for v in features if v != color_var]
    keyed = {v: grids[v].set_index(["lat", "lon"]) for v in shown}
    common = sorted(set.intersection(*(set(k.index) for k in keyed.values())))
    if not common:
        return pd.DataFrame()

    values, pct = {}, {}
    for v, k in keyed.items():
        series, pct[v] = trend_value(k.loc[common].reset_index())
        values[v] = series.to_numpy()
    significant = keyed[color_var].loc[common, "significant"].astype(bool).to_numpy()

    n = len(common)
    levels = [k for k in CLUSTER_LEVELS if k < n] if n >= MIN_POINTS_TO_CLUSTER else []
    if levels:
        X = np.column_stack([values[v] for v in features])
        spread = X.std(axis=0)
        X = (X - X.mean(axis=0)) / np.where(spread > 0, spread, 1.0)
        labels = cut_tree(linkage(X, method="ward"), n_clusters=levels)
    else:
        labels = np.zeros((n, 0), dtype=int)

    nodes = []

    def add(node_id, parent, label, depth, idx):
        members = [common[i] for i in idx]
        means = {v: float(values[v][idx].mean()) for v in shown}
        n_sig = int(significant[idx].sum())
        coords = place_name(*members[0]) if len(idx) == 1 and "°" in label else None
        if len(idx) > 1:
            where = position_word(members, common)
            count = f"{len(idx)} points ({n_sig} significant)"
        else:
            where = None if coords else f"{members[0][0]:.2f}°, {members[0][1]:.2f}°"
            count = "significant" if n_sig else "not significant"
        trends = " · ".join(f"{_var_info(v)['name']} {format_trend(means[v], v, pct[v])}" for v in shown)
        if depth == 0:
            trends = f"average of point trends: {trends}"
        nodes.append({
            "id": node_id, "parent": parent, "label": label, "depth": depth, "n_points": len(idx),
            "value": means[color_var], "n_significant": n_sig, "members": members,
            "position": position_word(members, common),
            "sentence": " · ".join(p for p in (label, where, trends, count) if p),
            **{f"mean_{v}": means[v] for v in features},
        })

    def north_first(groups):
        return sorted(groups, key=lambda idx: -np.mean([common[i][0] for i in idx]))

    def split(node_id, idx, level, depth, prefix):
        if level < labels.shape[1]:
            groups = [idx[labels[idx, level] == g] for g in np.unique(labels[idx, level])]
            if len(groups) == 1:  # this cut did not split the group: go to the next cut
                return split(node_id, idx, level + 1, depth, prefix)
            for j, g in enumerate(north_first(groups)):
                name = f"{prefix}{chr(65 + j)}" if depth == 0 else f"{prefix}{j + 1}"
                child = f"{node_id}/{name}"
                add(child, node_id, f"Zone {name}", depth + 1, g)
                split(child, g, level + 1, depth + 1, name)
            return
        for i in sorted(idx, key=lambda i: (-common[i][0], common[i][1])):
            lat, lon = common[i]
            add(f"{node_id}/{lat:.3f},{lon:.3f}", node_id, place_name(lat, lon), depth + 1, np.array([i]))

    add(ROOT, "", "All points", 0, np.arange(n))
    split(ROOT, np.arange(n), 0, 0, "")
    return pd.DataFrame(nodes)
