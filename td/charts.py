# SI-assisted: parts of this file were drafted with Claude (Anthropic) and reviewed by the team
"""Plotly figures. Owner: C (dashboard).

Contract:
    trend_figure(series, res, view="anomaly"|"raw") -> go.Figure
    trend_map_figure(grid_df, var_id) -> go.Figure                    # step 5
    box_figure(points, box) -> go.Figure

Every figure only draws numbers it is given (from analyze() / trend_grid() on real data);
nothing here computes a statistic of its own except the 12-month running mean.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go

RISING = "#c0392b"    # red
FALLING = "#2471a3"   # blue
NEUTRAL = "#7f8c8d"   # grey
LINE = "#34495e"
BAND = "rgba(52, 73, 94, 0.15)"


def _var_label(var_id: str) -> tuple[str, str]:
    """(name, units) from config.VARIABLES, falling back to the id while config is empty."""
    try:
        from td.config import VARIABLES
    except ImportError:
        VARIABLES = {}
    info = VARIABLES.get(var_id)
    if not info:
        from td.analyze import _var_info  # built-in names for the POWER variables until config lands

        info = _var_info(var_id)
    return info.get("name", var_id), info.get("units", "")


def _layout(fig: go.Figure, title: str, y_title: str, height: int = 420) -> go.Figure:
    fig.update_layout(
        title=dict(text=title, x=0, xanchor="left", font=dict(size=16)),
        height=height,
        margin=dict(l=10, r=10, t=50, b=10),
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.0, xanchor="right", x=1),
        plot_bgcolor="white",
        yaxis_title=y_title,
    )
    fig.update_xaxes(showgrid=True, gridcolor="#eee")
    fig.update_yaxes(showgrid=True, gridcolor="#eee", zeroline=True, zerolinecolor="#ccc")
    return fig


def _slope_band(trend: pd.Series, ci_decade) -> tuple[pd.Series, pd.Series] | None:
    """Lines through the middle of the trend line with the 95% CI's lowest and highest slope.

    Shows the range of slopes the data allow (pivoting around the record's midpoint).
    """
    if trend is None or len(trend) < 2 or ci_decade is None:
        return None
    lo, hi = ci_decade
    if lo is None or hi is None or not np.isfinite([lo, hi]).all():
        return None
    x = trend.index.year + (trend.index.month - 1) / 12.0
    x_mid = float(np.mean(x))
    y_mid = float(np.interp(x_mid, x, trend.to_numpy()))
    lower = y_mid + np.minimum(lo, hi) / 10.0 * (x - x_mid)
    upper = y_mid + np.maximum(lo, hi) / 10.0 * (x - x_mid)
    # Before the midpoint the "low" slope is actually higher, so take min/max per month.
    return (pd.Series(np.minimum(lower, upper), index=trend.index),
            pd.Series(np.maximum(lower, upper), index=trend.index))


def trend_figure(series: pd.Series, res: dict, view: str = "anomaly") -> go.Figure:
    """Monthly time series with its trend.

    view="anomaly": monthly anomalies, dashed OLS trend line and the 95% slope range.
    view="raw":     monthly values and their 12-month running mean (full windows only).
    """
    var_id = res.get("var_id", getattr(series, "name", "") or "")
    name, units = _var_label(var_id)
    unit_txt = f" ({units})" if units else ""
    fig = go.Figure()

    if view == "raw":
        s = series.astype(float).sort_index()
        fig.add_trace(go.Scatter(x=s.index, y=s.values, mode="lines", name="Monthly value",
                                 line=dict(color="#aab7b8", width=1)))
        rolling = s.rolling(12, min_periods=12).mean()
        fig.add_trace(go.Scatter(x=rolling.index, y=rolling.values, mode="lines", name="12-month average",
                                 line=dict(color=LINE, width=2.5)))
        return _layout(fig, f"{name}: monthly values", f"{name}{unit_txt}")

    anom = res.get("_anomalies")
    trend = res.get("_trend_line")
    if anom is None:
        from td.analyze import anomalies
        anom = anomalies(series)

    fig.add_trace(go.Scatter(x=anom.index, y=anom.values, mode="lines", name="Monthly anomaly",
                             line=dict(color="#aab7b8", width=1)))

    if trend is not None and len(trend):
        slope = res.get("slope_decade") or 0.0
        color = NEUTRAL if res.get("tier") == "none" else (RISING if slope > 0 else FALLING)
        band = _slope_band(trend, res.get("ci_decade"))
        if band is not None:
            lower, upper = band
            fig.add_trace(go.Scatter(x=upper.index, y=upper.values, mode="lines", line=dict(width=0),
                                     hoverinfo="skip", showlegend=False))
            fig.add_trace(go.Scatter(x=lower.index, y=lower.values, mode="lines", line=dict(width=0),
                                     fill="tonexty", fillcolor=BAND, name="95% range of the trend",
                                     hoverinfo="skip"))
        fig.add_trace(go.Scatter(x=trend.index, y=trend.values, mode="lines", name="Trend (OLS)",
                                 line=dict(color=color, width=3, dash="dash")))

    return _layout(fig, f"{name}: difference from the usual for each month",
                   f"Anomaly{unit_txt}")


def box_figure(points: list, box) -> go.Figure:
    """The region box with the grid points: filled = land (averaged), hollow = sea (skipped)."""
    west, south, east, north = box
    fig = go.Figure()
    fig.add_trace(go.Scattergeo(
        lon=[west, east, east, west, west], lat=[south, south, north, north, south],
        mode="lines", line=dict(color=LINE, width=2), name="Region", hoverinfo="skip"))

    land = [(lat, lon) for lat, lon, is_land in points if is_land]
    sea = [(lat, lon) for lat, lon, is_land in points if not is_land]
    if land:
        fig.add_trace(go.Scattergeo(lat=[p[0] for p in land], lon=[p[1] for p in land], mode="markers",
                                    marker=dict(size=9, color="#27ae60"), name=f"Land points used ({len(land)})",
                                    hovertemplate="%{lat:.2f}°, %{lon:.2f}°<extra>land</extra>"))
    if sea:
        fig.add_trace(go.Scattergeo(lat=[p[0] for p in sea], lon=[p[1] for p in sea], mode="markers",
                                    marker=dict(size=9, color="white", line=dict(color="#2980b9", width=1.5)),
                                    name=f"Sea points skipped ({len(sea)})",
                                    hovertemplate="%{lat:.2f}°, %{lon:.2f}°<extra>sea</extra>"))
    _fit_geo(fig, box)
    fig.update_layout(height=360, margin=dict(l=0, r=0, t=10, b=0),
                      legend=dict(orientation="h", yanchor="bottom", y=0, x=0))
    return fig


TREND_SCALE = [[0, FALLING], [0.5, "#f7f7f7"], [1, RISING]]
DIMMED = "#dcdcdc"


def zone_scale(grid_df: pd.DataFrame, var_id: str) -> tuple[pd.Series, str, float]:
    """(value per point, unit text, vmax) shared by the zone map and the zone tree: one colour scale for both.

    Value = % per decade when every point has one (relative variables), else the slope per decade.
    """
    _, units = _var_label(var_id)
    use_pct = "pct_decade" in grid_df and grid_df["pct_decade"].notna().all() and len(grid_df) > 0
    value = (grid_df["pct_decade"] if use_pct else grid_df["slope_decade"]).astype(float)
    unit_txt = "% per decade" if use_pct else f"{units} per decade".strip()
    vmax = float(np.nanmax(np.abs(value))) if len(grid_df) and np.isfinite(value).any() else 1.0
    return value, unit_txt, vmax or 1.0


def trend_map_figure(grid_df: pd.DataFrame, var_id: str, highlight=None) -> go.Figure:
    """Opposite-trends zone map: one marker per land point, red rising, blue falling.

    Marker colour = slope per decade (diverging, centred on zero); a black dot marks points that
    stay significant after the Benjamini-Hochberg FDR correction (grid_df.significant).
    highlight (optional): the (lat, lon) points of a selected zone; the other points turn grey.
    """
    name, _ = _var_label(var_id)
    df = grid_df.copy()
    value, unit_txt, vmax = zone_scale(df, var_id)

    q = df["q_fdr"] if "q_fdr" in df else pd.Series(np.nan, index=df.index)
    hover = [f"{lat:.2f}°, {lon:.2f}°<br>{v:+.3g} {unit_txt}<br>t-test p = {pt:.3f} · MK p = {pm:.3f}"
             f"<br>FDR q = {qq:.3f}{' · significant' if sig else ''}"
             for lat, lon, v, pt, pm, qq, sig in zip(df["lat"], df["lon"], value, df["p_ttest"], df["p_mk"],
                                                     q, df["significant"])]
    df["_value"], df["_hover"] = value.to_numpy(), hover
    if highlight is not None:
        chosen = {(round(float(a), 3), round(float(b), 3)) for a, b in highlight}
        df["_in"] = [(round(float(a), 3), round(float(b), 3)) in chosen for a, b in zip(df["lat"], df["lon"])]
    else:
        df["_in"] = True

    fig = go.Figure()
    other = df[~df["_in"]]
    if len(other):
        fig.add_trace(go.Scattergeo(
            lat=other["lat"], lon=other["lon"], mode="markers", name="Other zones", text=other["_hover"],
            hovertemplate="%{text}<extra></extra>",
            marker=dict(size=22, symbol="square", color=DIMMED, line=dict(color="#bbb", width=0.5))))
    shown = df[df["_in"]]
    fig.add_trace(go.Scattergeo(
        lat=shown["lat"], lon=shown["lon"], mode="markers",
        name="Selected zone" if len(other) else "Trend per point", text=shown["_hover"],
        hovertemplate="%{text}<extra></extra>",
        marker=dict(size=22, symbol="square", color=shown["_value"], cmin=-vmax, cmax=vmax,
                    colorscale=TREND_SCALE, line=dict(color="#555" if len(other) else "#999", width=0.8),
                    colorbar=dict(title=dict(text=unit_txt, side="right"), thickness=12))))
    sig = df[df["significant"].astype(bool) & df["_in"]]
    if len(sig):
        fig.add_trace(go.Scattergeo(lat=sig["lat"], lon=sig["lon"], mode="markers", hoverinfo="skip",
                                    marker=dict(size=6, color="black"), name="Significant (FDR 10%)"))

    if len(df):
        pad = 0.5
        _fit_geo(fig, (df["lon"].min() - pad, df["lat"].min() - pad, df["lon"].max() + pad, df["lat"].max() + pad))
    fig.update_layout(title=dict(text=f"{name}: where it rises and where it falls", x=0, font=dict(size=16)),
                      height=460, margin=dict(l=0, r=0, t=50, b=0),
                      legend=dict(orientation="h", yanchor="bottom", y=0, x=0))
    return fig


def cluster_tree_figure(tree_df: pd.DataFrame, var_id: str, vmax: float, unit_txt: str,
                        selected: str | None = None) -> go.Figure:
    """Trend-zone tree as a vertical icicle: all points on top, then zones, sub-zones and single points.

    Width = number of points; colour = the zone's average trend on the zone map's scale (pass the map's vmax
    from zone_scale), so tree and map read as one picture. selected = node id to zoom into.
    """
    t = tree_df
    short = [f"{v:+.1f}%" if "%" in unit_txt else f"{v:+.2g}" for v in t["value"]]
    fig = go.Figure(go.Icicle(
        ids=t["id"], parents=t["parent"], labels=t["label"], values=t["n_points"], branchvalues="total",
        customdata=np.column_stack([short, t["sentence"]]),
        texttemplate="<b>%{label}</b><br>%{customdata[0]}",
        hovertemplate="%{customdata[1]}<extra></extra>",
        marker=dict(colors=t["value"], colorscale=TREND_SCALE, cmin=-vmax, cmax=vmax, showscale=False,
                    line=dict(color="white", width=2)),
        tiling=dict(orientation="v"), maxdepth=3, level=selected or t["id"].iloc[0],
        root=dict(color="#f7f7f7"), textfont=dict(size=13), insidetextfont=dict(color="#222"),
    ))
    name, _ = _var_label(var_id)
    fig.update_layout(title=dict(text=f"Trend zones · colour: {name} ({unit_txt})", x=0, font=dict(size=16)),
                      height=520, margin=dict(l=0, r=0, t=50, b=0))
    return fig


def _fit_geo(fig: go.Figure, box) -> None:
    west, south, east, north = box
    pad_lon = max(1.0, (east - west) * 0.25)
    pad_lat = max(1.0, (north - south) * 0.25)
    fig.update_geos(
        projection_type="mercator", resolution=50, showcountries=True, countrycolor="#999",
        showland=True, landcolor="#f4f1ea", showocean=True, oceancolor="#e3f0fa", showlakes=False,
        lonaxis_range=[west - pad_lon, east + pad_lon], lataxis_range=[south - pad_lat, north + pad_lat])
