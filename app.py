# SI-assisted: parts of this file were drafted with Claude (Anthropic) and reviewed by the team
"""Trend Detective dashboard: 3 screens. Owner: C (dashboard). Step 3.

    streamlit run app.py              # real NASA POWER data (td.fetch.fetch_box)
    TD_SAMPLE=1 streamlit run app.py  # synthetic data from td.sample, no network

Screen 1: region (preset / drawn box) + years.  Screen 2: question or variable.
Screen 3: verdict, chart, map, cards, report.

Pieces owned by others (zone map, region comparison, second source, report) are called through
contracts; until their code lands the app skips that piece instead of failing.
"""
from __future__ import annotations

import os

import folium
import streamlit as st
from folium.plugins import Draw
from streamlit_folium import st_folium

from td import config
from td.analyze import _var_info, agreement, analyze, compare, correlate, verdict
from td.charts import box_figure, cluster_tree_figure, trend_figure, trend_map_figure, zone_scale
from td.fetch import FetchError, fetch_box

CUSTOM = "__custom__"
FORCE_SAMPLE = os.environ.get("TD_SAMPLE") == "1"
POWER_VARS = ["T2M", "PRECTOTCORR", "GWETTOP"]
DEFAULT_BOX = (7.5, 30.2, 11.6, 37.5)  # Tunisia; used only while config.REGIONS is empty
STEP_LABELS = {1: "1 · Pick a region", 2: "2 · Pick a question", 3: "3 · The verdict"}

st.set_page_config(page_title="Trend Detective", page_icon="🔎", layout="wide")


# ---------------------------------------------------------------- helpers (config, formatting)

def var_info(var_id: str) -> dict:
    info = dict(config.VARIABLES.get(var_id) or _var_info(var_id))  # built-in names until config lands
    info.setdefault("name", var_id)
    info.setdefault("units", "")
    info.setdefault("decimals", 2)
    return info


def available_variables() -> list[str]:
    """Variables the user can pick: everything in config, or the three POWER ids while config is empty."""
    return list(config.VARIABLES) or POWER_VARS


def region_type(box) -> str | None:
    try:
        return config.classify_box(box)
    except NotImplementedError:
        return None


def linked_variable(question_id: str, rtype: str | None) -> tuple[str | None, str]:
    try:
        return config.linked_for(question_id, rtype or "default")
    except (NotImplementedError, KeyError):
        return None, ""


def fmt_p(p) -> str:
    if p is None:
        return "–"
    return "< 0.001" if p < 0.001 else f"{p:.3f}"


def fmt_rate(value, var_id: str, signed: bool = True) -> str:
    info = var_info(var_id)
    if value is None:
        return "–"
    sign = "+" if signed else ""
    return f"{value:{sign}.{info['decimals']}f} {info['units']}".strip()


def validate(box, years) -> list[str]:
    west, south, east, north = box
    errors = []
    if not (-180 <= west <= 180 and -180 <= east <= 180 and -90 <= south <= 90 and -90 <= north <= 90):
        errors.append("Longitudes must be within ±180° and latitudes within ±90°.")
    if west >= east:
        errors.append("West must be smaller than east.")
    if south >= north:
        errors.append("South must be smaller than north.")
    for side, size in (("west–east", east - west), ("south–north", north - south)):
        if size > 0 and not 0.5 <= size <= 40:
            errors.append(f"The {side} side is {size:.1f}°; it must be between 0.5° and 40°.")
    if years[1] - years[0] + 1 < 10:
        errors.append("Pick at least 10 years: shorter records cannot show a trend reliably.")
    return errors


# ---------------------------------------------------------------- data (cached)

@st.cache_data(show_spinner=False)
def load_box(box: tuple, start_year: int, end_year: int):
    """(BoxData, is_sample). Real NASA data unless TD_SAMPLE=1 or the data layer is not merged yet."""
    if not FORCE_SAMPLE:
        try:
            return fetch_box(box, start_year, end_year), False
        except NotImplementedError:
            pass  # step 1 not merged yet: fall back to sample data, clearly labelled
    from td.sample import sample_box_data

    bd = sample_box_data(box)
    keep = slice(str(start_year), str(end_year))
    bd.data = bd.data.loc[keep]
    bd.point_data = {k: v.loc[keep] for k, v in bd.point_data.items()}
    return bd, True


@st.cache_data(show_spinner=False)
def analyze_box(box: tuple, start_year: int, end_year: int, var_id: str):
    bd, _ = load_box(box, start_year, end_year)
    return analyze(bd.data[var_id], var_id)


@st.cache_data(show_spinner=False)
def zone_grid(box: tuple, start_year: int, end_year: int, var_id: str):
    """trend_grid() per land point, or None while step 5 is not merged / too few points."""
    from td.trendmap import trend_grid

    bd, _ = load_box(box, start_year, end_year)
    if len(bd.point_data) < 2:
        return None
    try:
        return trend_grid(bd.point_data, var_id, fdr_alpha=0.10)
    except NotImplementedError:
        return None


@st.cache_data(show_spinner=False)
def zone_tree(box: tuple, start_year: int, end_year: int, features: tuple, color_var: str):
    """cluster_tree() of the zone grids, or None when a grid is missing or there are too few points."""
    from td.trendmap import cluster_tree

    grids = {v: zone_grid(box, start_year, end_year, v) for v in dict.fromkeys((color_var, *features))}
    if any(g is None or g.empty for g in grids.values()):
        return None
    return cluster_tree(grids, features=list(features), color_var=color_var)


@st.cache_data(show_spinner=False)
def second_source(var_id: str, box: tuple, start_year: int, end_year: int):
    """(series, None) or (None, reason). Never raises: the app must work when Giovanni is down."""
    try:
        from td.giovanni import fetch_series_giovanni

        return fetch_series_giovanni(var_id, box, start_year, end_year), None
    except NotImplementedError:
        return None, "The second source is not connected yet."
    except Exception as exc:  # network, login or quota problems
        return None, f"The second source could not be reached ({type(exc).__name__})."


# ---------------------------------------------------------------- state

WIDGET_KEYS = ("region_id", "west", "south", "east", "north", "years", "mode", "question_id", "var_id", "view",
               "cluster_vars", "zone")


def init_state():
    ss = st.session_state
    # Streamlit forgets a widget's value when the widget is not drawn (e.g. the box inputs on screen 3).
    # Re-assigning keeps every choice across screens.
    for key in WIDGET_KEYS:
        if key in ss:
            ss[key] = ss[key]
    ss.setdefault("step", 1)
    first = next(iter(config.REGIONS), CUSTOM)
    ss.setdefault("region_id", first)
    box = config.REGIONS[first]["box"] if first in config.REGIONS else DEFAULT_BOX
    for key, value in zip(("west", "south", "east", "north"), box):
        ss.setdefault(key, float(value))
    ss.setdefault("years", (config.FIRST_YEAR, config.LAST_YEAR))
    ss.setdefault("mode", "question")
    ss.setdefault("question_id", next(iter(config.QUESTIONS), None))
    ss.setdefault("var_id", available_variables()[0])
    ss.setdefault("view", "Anomalies")


def set_box(box):
    for key, value in zip(("west", "south", "east", "north"), box):
        st.session_state[key] = round(float(value), 2)


def on_region_change():
    rid = st.session_state.region_id
    if rid in config.REGIONS:
        set_box(config.REGIONS[rid]["box"])


def current_box() -> tuple:
    ss = st.session_state
    return (ss.west, ss.south, ss.east, ss.north)


def go(step: int):
    st.session_state.step = step


def new_case():
    st.session_state.clear()


def region_name() -> str:
    rid = st.session_state.region_id
    if rid in config.REGIONS:
        return config.REGIONS[rid]["name"]
    w, s, e, n = current_box()
    return f"Custom box ({w:.1f}°, {s:.1f}°) to ({e:.1f}°, {n:.1f}°)"


def chosen_variables() -> tuple[str, str | None, str]:
    """(primary var, linked var or None, why linked) for the current question / variable."""
    ss = st.session_state
    if ss.mode == "question" and ss.question_id in config.QUESTIONS:
        primary = config.QUESTIONS[ss.question_id]["primary"]
        linked, why = linked_variable(ss.question_id, region_type(current_box()))
        return primary, linked, why
    return ss.var_id, None, ""


# ---------------------------------------------------------------- screen 1: region and years

def screen_region():
    st.subheader("Where should we investigate?")
    left, right = st.columns([1, 2], gap="large")

    with left:
        options = list(config.REGIONS) + [CUSTOM]
        st.radio("Region", options, key="region_id", on_change=on_region_change,
                 format_func=lambda r: "✏️ Draw your own box" if r == CUSTOM else config.REGIONS[r]["name"])
        rid = st.session_state.region_id
        if rid in config.REGIONS:
            st.caption(config.REGIONS[rid].get("blurb", ""))
        else:
            st.caption("Draw a rectangle on the map with the ■ tool, or type the corners below.")

    with right:
        drawn = region_map(rid == CUSTOM)
        if drawn and drawn != current_box():
            set_box(drawn)
            st.rerun()

    with left:
        c1, c2 = st.columns(2)
        c1.number_input("West (°E)", -180.0, 180.0, step=0.1, key="west", format="%.2f")
        c2.number_input("East (°E)", -180.0, 180.0, step=0.1, key="east", format="%.2f")
        c1.number_input("South (°N)", -90.0, 90.0, step=0.1, key="south", format="%.2f")
        c2.number_input("North (°N)", -90.0, 90.0, step=0.1, key="north", format="%.2f")
        st.slider("Years", config.FIRST_YEAR, config.LAST_YEAR, key="years")
        y0, y1 = st.session_state.years
        st.caption(f"{y1 - y0 + 1} years of monthly data ({(y1 - y0 + 1) * 12} months).")

        errors = validate(current_box(), st.session_state.years)
        for msg in errors:
            st.error(msg)
        st.button("Next →", type="primary", disabled=bool(errors), on_click=go, args=(2,),
                  width="stretch")


def region_map(drawing: bool):
    """Folium map of the current box. In drawing mode returns the drawn rectangle as a box, else None."""
    west, south, east, north = current_box()
    m = folium.Map(location=[(south + north) / 2, (west + east) / 2])
    folium.Rectangle([[south, west], [north, east]], color="#c0392b", weight=2, fill=True,
                     fill_opacity=0.08, tooltip=region_name()).add_to(m)
    m.fit_bounds([[south, west], [north, east]], padding=(20, 20))
    if drawing:
        Draw(draw_options={"polyline": False, "polygon": False, "circle": False, "marker": False,
                           "circlemarker": False, "rectangle": True},
             edit_options={"edit": False, "remove": False}).add_to(m)
    out = st_folium(m, height=460, use_container_width=True, key=f"map_{drawing}",
                    returned_objects=["last_active_drawing"] if drawing else [])
    if not drawing or not out:
        return None
    shape = out.get("last_active_drawing") or {}
    coords = (shape.get("geometry") or {}).get("coordinates")
    if not coords:
        return None
    lons = [c[0] for c in coords[0]]
    lats = [c[1] for c in coords[0]]
    return tuple(round(v, 2) for v in (min(lons), min(lats), max(lons), max(lats)))


# ---------------------------------------------------------------- screen 2: question or variable

def screen_question():
    st.subheader(f"What do you want to know about {region_name()}?")
    rtype = region_type(current_box())
    modes = ["question", "variable"] if config.QUESTIONS else ["variable"]
    if st.session_state.mode not in modes:
        st.session_state.mode = modes[0]
    st.radio("How", modes, key="mode", horizontal=True, label_visibility="collapsed",
             format_func=lambda m: "Ask a question" if m == "question" else "Explore any variable")

    if st.session_state.mode == "question":
        qids = list(config.QUESTIONS)
        if st.session_state.question_id not in qids:
            st.session_state.question_id = qids[0]
        st.radio("Question", qids, key="question_id",
                 format_func=lambda q: f"{config.QUESTIONS[q].get('icon', '')} {config.QUESTIONS[q]['label']}")
        primary, linked, why = chosen_variables()
        line = f"Main variable: **{var_info(primary)['name']}**"
        if linked:
            line += f" · checked against **{var_info(linked)['name']}**"
        st.caption(line)
        if why:
            st.caption(f"Why: {why}" + (f" (region type: {rtype})" if rtype else ""))
    else:
        vids = available_variables()
        if st.session_state.var_id not in vids:
            st.session_state.var_id = vids[0]
        st.selectbox("Variable", vids, key="var_id", format_func=lambda v: var_info(v)["name"])
        info = var_info(st.session_state.var_id)
        if info.get("definition"):
            st.caption(f"{info['definition']} Units: {info['units']}.")

    later = getattr(config, "COMING_LATER", [])
    if later:
        with st.expander("Coming later"):
            for item in later:
                st.markdown(f"- {item}")

    c1, c2 = st.columns(2)
    c1.button("← Back", on_click=go, args=(1,), width="stretch")
    c2.button("Investigate →", type="primary", on_click=go, args=(3,), width="stretch")


# ---------------------------------------------------------------- screen 3: verdict

def screen_verdict():
    box = current_box()
    y0, y1 = st.session_state.years
    primary, linked, why = chosen_variables()
    info = var_info(primary)

    try:
        with st.spinner(f"Fetching NASA data for {region_name()} and running the tests…"):
            bd, is_sample = load_box(box, y0, y1)
            res = analyze_box(box, y0, y1, primary)
    except FetchError as exc:
        st.error(f"Could not get the data: {exc}")
        nav_buttons()
        return
    except NotImplementedError:
        st.error("The data layer or stats engine is not merged into this branch yet.")
        nav_buttons()
        return
    except ValueError as exc:
        st.error(str(exc))
        nav_buttons()
        return

    if is_sample:
        st.warning("**Sample data, not NASA data.** These numbers are synthetic and only for building the app.",
                   icon="🧪")

    st.subheader(f"{info['name']} · {region_name()} · {y0}–{y1}")
    words = verdict(res)
    verdict_card(res, words)
    extra_lines(res, primary, box, y0, y1)
    metrics_row(res, primary)

    st.radio("Chart", ["Anomalies", "Raw values"], key="view", horizontal=True, label_visibility="collapsed")
    view = "anomaly" if st.session_state.view == "Anomalies" else "raw"
    st.plotly_chart(trend_figure(bd.data[primary], res, view=view), width="stretch")
    record_note(res)

    zone_map(box, y0, y1, primary, res)

    link = None
    if linked and linked in bd.data:
        link = {"var_id": linked, "why": why, **correlate(bd.data[primary], bd.data[linked])}

    c1, c2 = st.columns(2)
    with c1:
        variable_card(primary)
    with c2:
        if link:
            linked_box(link)
        st.plotly_chart(box_figure(bd.points, box), width="stretch", config={"scrollZoom": False})
        st.caption(f"{bd.points_used} of {bd.points_total} grid points are land and were averaged "
                   f"(weighted by cos(latitude)).")

    how_it_works()
    downloads(bd, res, words, primary, link)
    nav_buttons()


def verdict_card(res, words):
    text = f"### {words['headline']}\n{words['detail']}"
    if res["tier"] == "significant":
        st.info(text, icon="🔎")
    elif res["tier"] == "suggestive":
        st.warning(text, icon="🤔")
    else:
        with st.container(border=True):
            st.markdown(text)


def extra_lines(res, var_id, box, y0, y1):
    """Step 6 (parent region sentence) and step 7 (second source); each is skipped until it lands."""
    rid = st.session_state.region_id
    parent = config.REGIONS.get(rid, {}).get("parent")
    if parent in config.REGIONS:
        try:
            parent_res = analyze_box(tuple(config.REGIONS[parent]["box"]), y0, y1, var_id)
            st.markdown(f"**Compared with its region:** "
                        f"{compare(res, parent_res, config.REGIONS[rid]['name'], config.REGIONS[parent]['name'])}")
        except (NotImplementedError, FetchError, ValueError):
            pass

    cross = var_info(var_id).get("cross_check")
    if cross:
        series, reason = second_source(cross, box, y0, y1)
        other = None
        if series is not None:
            try:
                other = analyze(series, cross)
            except ValueError as exc:
                reason = str(exc)
        try:
            state = agreement(res, other)
        except NotImplementedError:
            return
        name = var_info(cross)["name"]
        text = {"agree": f"✅ Two sources agree: {name} shows the same direction.",
                "disagree": f"⚠️ Sources disagree: {name} points the other way, so treat this with caution.",
                "single": f"ℹ️ Single source only. {reason or ''}".strip()}.get(state, "")
        st.markdown(text)


def metrics_row(res, var_id):
    lo, hi = res["ci_decade"]
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Trend per decade (OLS)", fmt_rate(res["slope_decade"], var_id),
              help="Ordinary least squares on monthly anomalies, Newey-West standard errors.")
    m1.caption(f"95% CI: {fmt_rate(lo, var_id)} to {fmt_rate(hi, var_id)}"
               + (f" · {res['pct_decade']:+.1f}% of the mean" if res.get("pct_decade") is not None else ""))
    m2.metric("t-test p-value", fmt_p(res["p_ttest"]), help="Chance of a slope this large if there were no trend.")
    m3.metric("Mann-Kendall p-value", fmt_p(res["p_mk"]),
              help="Rank-based test (Hamed-Rao), robust to outliers and autocorrelation.")
    m4.metric("Sen's slope per decade", fmt_rate(res["sen_decade"], var_id),
              help="Median of all pairwise slopes: a robust check on the OLS rate.")
    if not res.get("tests_agree", True):
        st.caption("⚠️ The two methods disagree on the direction of the trend.")


def record_note(res):
    note = (f"Record: {res['start']} to {res['end']} · {res['span_years']:.0f} years · "
            f"{res['n_months']} months used · {res['missing_months']} missing")
    yts = res.get("years_to_significance")
    if res["tier"] != "significant" and yts is not None and yts <= 50:
        note += f" · about {yts:.0f} more years of data would be needed to be sure, if this rate held"
    st.caption(note)


def zone_map(box, y0, y1, var_id, res):
    grid = zone_grid(box, y0, y1, var_id)
    if grid is None or grid.empty:
        return
    tree = zone_controls(box, y0, y1, var_id, len(grid))
    if tree is None or tree.empty:
        st.plotly_chart(trend_map_figure(grid, var_id), width="stretch", config={"scrollZoom": False})
    else:
        zone_tree_and_map(grid, tree, var_id)
    rising = int((grid["significant"] & (grid["slope_decade"] > 0)).sum())
    falling = int((grid["significant"] & (grid["slope_decade"] < 0)).sum())
    st.caption(f"Each square is one NASA POWER grid point: red rising, blue falling. A black dot means the trend "
               f"there is significant after correcting for testing {len(grid)} points at once (FDR 10%). "
               f"Significant: {rising} rising, {falling} falling.")
    if rising and falling and res["tier"] == "none":
        st.info("Parts of the region move in opposite directions, which can cancel out in the regional average.")


def zone_controls(box, y0, y1, var_id, n_points):
    """'Group points by' (the expert's parameters) and 'Zone' (drill-down) above the tree and map.

    The selectbox drives both views: a click inside a Plotly icicle zooms it in the browser but does not
    reach Streamlit, so it cannot drive the map.
    """
    from td.trendmap import MIN_POINTS_TO_CLUSTER, ROOT

    if var_id not in POWER_VARS or n_points < MIN_POINTS_TO_CLUSTER:
        return None
    ss = st.session_state
    if not ss.get("cluster_vars") or any(v not in POWER_VARS for v in ss.cluster_vars):
        ss.cluster_vars = [var_id]
    st.markdown("#### Trend zones: where it rises and where it falls")
    c1, c2 = st.columns([2, 3], gap="large")
    c1.multiselect("Group points by the trend of", POWER_VARS, key="cluster_vars",
                   format_func=lambda v: var_info(v)["name"],
                   help="Grid points whose trends look alike are grouped into zones (Ward hierarchical "
                        "clustering), then sub-zones, down to single points.")
    tree = zone_tree(box, y0, y1, tuple(ss.cluster_vars) or (var_id,), var_id)
    if tree is None or tree.empty:
        return None
    labels = dict(zip(tree["id"], zip(tree["label"], tree["depth"], tree["n_points"])))
    if ss.get("zone") not in labels:
        ss.zone = ROOT
    c2.selectbox("Zone", list(labels), key="zone",
                 format_func=lambda i: " " * labels[i][1] + labels[i][0]
                 + (f" ({labels[i][2]} points)" if labels[i][2] > 1 else ""))
    return tree


def zone_tree_and_map(grid, tree, var_id):
    """Tree on the left (control), map on the right (result), one colour scale and one colour bar."""
    from td.trendmap import ROOT

    zone = st.session_state.zone
    node = tree.set_index("id").loc[zone]
    _, unit_txt, vmax = zone_scale(grid, var_id)
    left, right = st.columns([2, 3], gap="large")
    with left:
        st.plotly_chart(cluster_tree_figure(tree, var_id, vmax, unit_txt, selected=zone), width="stretch")
        st.caption("Width = number of grid points. Colour = the average trend of a zone's points, on the "
                   "map's scale. Zones group points whose trends look alike: a description, not a test.")
    with right:
        st.markdown(f"**{node['sentence']}**")
        highlight = None if zone == ROOT else node["members"]
        st.plotly_chart(trend_map_figure(grid, var_id, highlight=highlight), width="stretch",
                        config={"scrollZoom": False})


def variable_card(var_id):
    info = var_info(var_id)
    with st.container(border=True):
        st.markdown(f"#### {info['name']}")
        rows = [("What it is", info.get("definition")), ("Source", info.get("source")),
                ("Units", info.get("units")), ("Record", info.get("record")),
                ("Why we chose it", info.get("why")), ("Caveat", info.get("caveat"))]
        for label, value in rows:
            if value:
                st.markdown(f"**{label}:** {value}")


def linked_box(link):
    """link = {var_id, why, r, n}: the linked variable and correlate() of the two anomaly series."""
    with st.container(border=True):
        st.markdown(f"#### Linked variable: {var_info(link['var_id'])['name']}")
        if link["why"]:
            st.markdown(link["why"])
        if link["r"] is None:
            st.markdown("Not enough overlapping months to compare.")
        else:
            st.markdown(f"Month-to-month anomalies move together with **r = {link['r']:+.2f}** ({link['n']} months). "
                        "A link like this is consistent with a connection; it is **not proof of cause**.")


def how_it_works():
    with st.expander("How it works"):
        st.markdown(
            "1. **Data**: NASA POWER monthly values (MERRA-2 reanalysis) on a grid of points inside the box; "
            "sea points are skipped and land points averaged with cos(latitude) weights.\n"
            "2. **Anomalies**: each month minus its usual value for that calendar month, so seasons don't "
            "look like trends.\n"
            "3. **Rate of change**: a straight-line fit (OLS) per decade, with a 95% confidence interval and a "
            "t-test using Newey-West errors (neighbouring months are not independent).\n"
            "4. **Second test**: Mann-Kendall (Hamed-Rao modification) and Sen's slope, which don't assume a "
            "straight line or normal noise.\n"
            "5. **Verdict**: *significant* when both tests give p < 0.05 and agree on direction; *possibly* when "
            "either gives p < 0.10; otherwise *no clear trend yet*.\n"
            "6. **Zones**: the same tests on every grid point, corrected for multiple testing "
            "(Benjamini-Hochberg FDR, 10%).")


def downloads(bd, res, words, primary, link):
    try:
        from td.report import csv_bytes, markdown_report

        y0, y1 = st.session_state.years
        case = {"region": region_name(), "box": current_box(), "years": (y0, y1), "var_id": primary,
                "question_id": st.session_state.question_id if st.session_state.mode == "question" else None,
                "points_used": bd.points_used, "points_total": bd.points_total}
        report = markdown_report(case, res, words, linked=link)
        data = csv_bytes(bd.data[primary], res)
    except NotImplementedError:
        return
    c1, c2 = st.columns(2)
    c1.download_button("⬇️ Case report (Markdown)", report, file_name="trend_detective_report.md",
                       width="stretch")
    c2.download_button("⬇️ Data (CSV)", data, file_name=f"trend_detective_{primary}.csv",
                       width="stretch")


def nav_buttons():
    c1, c2 = st.columns(2)
    c1.button("← Back", on_click=go, args=(2,), width="stretch")
    c2.button("🔄 New case", on_click=new_case, width="stretch")


# ---------------------------------------------------------------- page

init_state()
st.title("🔎 Trend Detective")
st.caption("Is it really changing? Pick a region, ask a question, get a tested answer from NASA data.")
step = st.session_state.step
st.progress(step / 3, text=STEP_LABELS[step])

{1: screen_region, 2: screen_question, 3: screen_verdict}[step]()

st.divider()
st.caption("Data: NASA POWER (MERRA-2 reanalysis), 1981–2025. Built for NASA Space Apps 2026. "
           "SI-assisted: parts of this app were drafted with Claude (Anthropic) and reviewed by the team.")
