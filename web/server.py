# SI-assisted: parts of this file were drafted with Claude (Anthropic) and reviewed by the team
"""Map-first web UI: a small JSON API over td.* plus the static page. Owner: C (dashboard).

    python -m web.server            # then open http://localhost:8600

Standard library only (no new dependencies). The page (web/static/) draws a full-screen map; the
user picks NASA POWER grid points (freehand lasso or one by one) and a question or variable; the
server fetches exactly those points, averages the land ones and runs the same tests as app.py.

API
    GET  /api/meta                     years, variables
    POST /api/area     {points}        region type + questions ranked for it
    POST /api/point    {lat, lon}      one NASA POWER cell: land/sea, 1981-2025 mean of each variable
    POST /api/analyze  {points, var_id, linked, years}
                                       verdict, numbers, Plotly figures, per-point info, zones
    POST /api/crosscheck {points, var_id, years}
                                       same variable from a second NASA dataset (AIRS / GPM IMERG via
                                       Giovanni) over the shared years, and whether the two agree
    POST /api/scan       {points, years}
                                       every variable tested on the area (drives the suggested questions)
    POST /api/explain    {points, var_id, question_id, years, cross}
                                       plain-language summary + next questions (Gemini or a template;
                                       only numbers the app computed are allowed)
"""
from __future__ import annotations

import json
import math
import os
import sys
import traceback
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import plotly  # noqa: E402
import plotly.io as pio  # noqa: E402

from td import config  # noqa: E402
from td import questions as QCAT  # noqa: E402
from td.analyze import analyze, correlate, verdict  # noqa: E402
from td.charts import trend_figure  # noqa: E402
from td.fetch import FetchError, _snap, area_mean, fetch_point, is_land  # noqa: E402

STATIC = Path(__file__).resolve().parent / "static"
PLOTLY_JS = Path(plotly.__file__).resolve().parent / "package_data" / "plotly.min.js"
PORT = int(os.environ.get("TD_PORT", "8600"))
MAX_POINTS = getattr(config, "MAX_POINTS", 30)
MIN_YEARS = 10
WORKERS = 4

# Used only while td/config.py (owner D) is still empty; config always wins when it has content.
FALLBACK_VARIABLES = {
    "T2M": {"name": "Air temperature", "units": "°C", "decimals": 2,
            "definition": "Monthly mean air temperature 2 m above the ground.",
            "source": "NASA POWER (MERRA-2 reanalysis), monthly"},
    "PRECTOTCORR": {"name": "Rainfall", "units": "mm/day", "decimals": 2,
                    "definition": "Average daily precipitation in each month (bias-corrected).",
                    "source": "NASA POWER (MERRA-2 reanalysis), monthly"},
    "GWETTOP": {"name": "Topsoil wetness", "units": "0 to 1", "decimals": 3,
                "definition": "How wet the top 5 cm of soil is, from 0 (dry) to 1 (saturated).",
                "source": "NASA POWER (MERRA-2 reanalysis), monthly"},
    "T2M_MAX": {"name": "Hottest temperature of the month", "units": "°C", "decimals": 2,
                "definition": "The highest air temperature (2 m above the ground) reached in each month.",
                "source": "NASA POWER (MERRA-2 reanalysis), monthly"},
    "T2M_MIN": {"name": "Coldest temperature of the month", "units": "°C", "decimals": 2,
                "definition": "The lowest air temperature (2 m above the ground) reached in each month.",
                "source": "NASA POWER (MERRA-2 reanalysis), monthly"},
    "FROST_DAYS": {"name": "Frost days", "units": "days/month", "decimals": 2,
                   "definition": "Number of days in the month when the air temperature drops below 0 °C.",
                   "source": "NASA POWER (MERRA-2 reanalysis), monthly"},
    "PRECSNOLAND": {"name": "Snowfall", "units": "mm/day", "decimals": 3,
                    "definition": "Average daily snowfall over land, as millimetres of melted water.",
                    "source": "NASA POWER (MERRA-2 reanalysis), monthly"},
    "SNODP": {"name": "Snow depth", "units": "cm", "decimals": 2,
              "definition": "Average depth of the snow lying on the ground.",
              "source": "NASA POWER (MERRA-2 reanalysis), monthly"},
    "RH2M": {"name": "Humidity", "units": "%", "decimals": 2,
             "definition": "Relative humidity of the air 2 m above the ground.",
             "source": "NASA POWER (MERRA-2 reanalysis), monthly"},
}
# Region-aware question catalog (td/questions.py), in the {linked: {default: ...}} shape config.QUESTIONS uses.
FALLBACK_QUESTIONS = {
    qid: {"label": q["label"], "primary": q["primary"], "linked": {"default": q["linked"]},
          "why_linked": {"default": q["why"]}}
    for qid, q in QCAT.CATALOG.items()
}


# ------------------------------------------------------------------ content helpers

def variables() -> dict:
    out = {}
    for vid in config.VARIABLES or FALLBACK_VARIABLES:
        info = dict(FALLBACK_VARIABLES.get(vid, {}))
        info.update(config.VARIABLES.get(vid, {}))
        info.setdefault("name", vid)
        info.setdefault("units", "")
        info.setdefault("decimals", 2)
        out[vid] = {k: v for k, v in info.items() if isinstance(v, (str, int, float, bool)) or v is None}
    return out


def questions() -> dict:
    return config.QUESTIONS or FALLBACK_QUESTIONS


def region_type(box) -> str | None:
    try:
        return config.classify_box(box)
    except (NotImplementedError, KeyError, ValueError):
        return None


def linked_for(qid: str, rtype: str | None) -> tuple[str | None, str]:
    try:
        return config.linked_for(qid, rtype or "default")
    except (NotImplementedError, KeyError):
        q = questions().get(qid, {})
        linked, why = q.get("linked", {}), q.get("why_linked", {})
        return linked.get(rtype, linked.get("default")), why.get(rtype, why.get("default", ""))


def bbox(points) -> tuple[float, float, float, float]:
    lats = [p[0] for p in points]
    lons = [p[1] for p in points]
    return (min(lons) - 0.3125, min(lats) - 0.25, max(lons) + 0.3125, max(lats) + 0.25)


def area_means(data: pd.DataFrame) -> dict:
    """Long-term average of each variable over the picked land points: what kind of climate is this?"""
    return {col: num(data[col].mean()) for col in data.columns if data[col].notna().any()}


def ranked_questions(points, means: dict | None = None) -> dict:
    """Questions that fit the area's climate, most relevant first. Before the data is in: a short default list."""
    qs = questions()
    climate = QCAT.climate_type(means) if means else None
    if config.QUESTIONS:  # team catalog (D) wins when it exists
        rtype = region_type(bbox(points)) if points else None
        order = list(qs)
    else:
        rtype = climate["type"] if climate else None
        order = [q for q in QCAT.relevant_questions(means) if q in qs]
    names = variables()
    out = []
    for qid in order:
        q = qs[qid]
        linked, why = linked_for(qid, rtype)
        out.append({"id": qid, "label": q["label"], "primary": q["primary"], "linked": linked, "why": why,
                    "vars": f"{names.get(q['primary'], {}).get('name', q['primary'])}"
                            + (f" · compared with {names.get(linked, {}).get('name', linked).lower()}" if linked else "")})
    return {"region_type": rtype, "climate": climate, "questions": out}


# ------------------------------------------------------------------ analysis

def clean_points(raw) -> list[tuple[float, float]]:
    if not isinstance(raw, list) or not raw:
        raise FetchError("Pick at least one grid point on the map.")
    pts = []
    for p in raw:
        try:
            lat, lon = float(p[0]), float(p[1])
        except (TypeError, ValueError, IndexError):
            raise FetchError("A picked point is not a (lat, lon) pair.") from None
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            raise FetchError("A picked point is outside the map.")
        snapped = _snap(lat, lon)
        if snapped not in pts:
            pts.append(snapped)
    if len(pts) > MAX_POINTS:
        raise FetchError(f"Pick at most {MAX_POINTS} points (you picked {len(pts)}); NASA POWER is asked once per point.")
    return pts


def fetch_points(pts, y0, y1) -> dict:
    def one(pt):
        try:
            return pt, fetch_point(pt[0], pt[1], y0, y1), None
        except FetchError as err:
            return pt, None, err

    frames, errors = {}, []
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        for pt, df, err in pool.map(one, pts):
            if err is not None:
                errors.append(err)
            else:
                frames[pt] = df
    if errors:
        raise FetchError(f"NASA POWER did not answer for {len(errors)} of {len(pts)} points. Try again in a minute "
                         f"(points already downloaded are kept). First error: {errors[0]}")
    return frames


def point_summary(body) -> dict:
    """What NASA POWER recorded at one grid cell over the full record: land or sea, and the mean of each variable."""
    (lat, lon), = clean_points([[body.get("lat"), body.get("lon")]])
    y0, y1 = config.FIRST_YEAR, config.LAST_YEAR
    df = fetch_point(lat, lon, y0, y1)
    months = pd.date_range(f"{y0}-01-01", f"{y1}-12-01", freq="MS")
    df = df.reindex(months)
    first = df.dropna(how="all").index
    return {
        "lat": lat, "lon": lon, "land": bool(is_land(df)),
        "years": [y0, y1],
        "months": int(df.notna().any(axis=1).sum()),
        "first": first[0].strftime("%Y-%m") if len(first) else None,
        "last": first[-1].strftime("%Y-%m") if len(first) else None,
        "means": {col: num(df[col].mean()) for col in df.columns},
        "missing": {col: int(df[col].isna().sum()) for col in df.columns},
    }


def num(v):
    if v is None:
        return None
    if isinstance(v, (bool, np.bool_)):
        return bool(v)
    if isinstance(v, (int, float, np.integer, np.floating)):
        f = float(v)
        return None if math.isnan(f) or math.isinf(f) else f
    if isinstance(v, (tuple, list)):
        return [num(x) for x in v]
    return v


def figure_json(fig) -> dict:
    # The panel already names the variable, so drop the title and put the legend under the plot.
    fig.update_layout(height=280, margin=dict(l=8, r=8, t=8, b=8), title_text="",
                      font=dict(family="Archivo, Helvetica, Arial, sans-serif", size=11),
                      legend=dict(font=dict(size=10), orientation="h", yanchor="top", y=-0.1, x=0, xanchor="left"))
    return json.loads(pio.to_json(fig))


def area_data(body):
    """Validate the request and return (pts, land frames, area-mean data, var_id, y0, y1, months)."""
    pts = clean_points(body.get("points"))
    var_id = str(body.get("var_id", ""))
    if var_id not in variables():
        raise FetchError(f"Unknown variable {var_id!r}.")
    try:
        y0, y1 = (int(y) for y in body.get("years", [config.FIRST_YEAR, config.LAST_YEAR]))
    except (TypeError, ValueError):
        raise FetchError("Years must be two whole numbers.") from None
    if not (config.FIRST_YEAR <= y0 <= y1 <= config.LAST_YEAR) or y1 - y0 + 1 < MIN_YEARS:
        raise FetchError(f"Pick at least {MIN_YEARS} years between {config.FIRST_YEAR} and {config.LAST_YEAR}.")

    frames = fetch_points(pts, y0, y1)
    land = {pt: df for pt, df in frames.items() if is_land(df)}
    if not land:
        raise FetchError("All picked points are sea. Pick points over land.")
    months = pd.date_range(f"{y0}-01-01", f"{y1}-12-01", freq="MS", name="month")
    return pts, land, area_mean(land).reindex(months), var_id, y0, y1, months


# ------------------------------------------------------------------ cross-check (step 7)

# Same quantity, second independent NASA dataset (Giovanni). Used until config.VARIABLES has cross_check.
SECOND_SOURCE = {"T2M": "AIRS_T", "PRECTOTCORR": "IMERG"}
PRIMARY_LABEL = "MERRA-2 reanalysis (NASA POWER)"
INDEPENDENCE_NOTE = {
    "AIRS_T": "AIRS measures temperature from space; MERRA-2 is a weather model that also uses AIRS radiances, "
              "so the two are partly, not fully, independent.",
    "IMERG": "IMERG combines several satellites with rain gauges; MERRA-2's rain is corrected with gauge data too, "
             "so the two are partly, not fully, independent.",
}


def second_source_for(var_id: str) -> str | None:
    return (config.VARIABLES.get(var_id, {}) or {}).get("cross_check") or SECOND_SOURCE.get(var_id)


def annual_anomalies(series: pd.Series) -> pd.Series:
    """Calendar-year mean of the monthly anomalies, only years with at least 9 months."""
    from td.analyze import anomalies

    a = anomalies(series.dropna())
    g = a.groupby(a.index.year)
    return g.mean()[g.count() >= 9]


def cross_check_figure(a: pd.Series, b: pd.Series, name_a: str, name_b: str, units: str) -> dict:
    import plotly.graph_objects as go

    fig = go.Figure()
    for s, name, col, dash in ((a, name_a, "#046460", None), (b, name_b, "#C2410C", "dash")):
        ya = annual_anomalies(s)
        fig.add_trace(go.Scatter(x=list(ya.index), y=list(ya.values), mode="lines+markers", name=name,
                                 line=dict(color=col, width=2.5, dash=dash), marker=dict(size=5)))
    fig.add_hline(y=0, line=dict(color="#9A9B9F", width=1))
    fig.update_layout(template="plotly_white", yaxis_title=f"Difference from usual ({units})", xaxis_title=None)
    out = figure_json(fig)
    out["layout"]["height"] = 240
    return out


def cross_check(body) -> dict:
    """Same variable from a second NASA dataset, over the years both cover; never raises for Giovanni trouble."""
    from td.analyze import agreement

    pts, land, data, var_id, y0, y1, months = area_data(body)
    info = variables()[var_id]
    other_id = second_source_for(var_id)
    if not other_id:
        return {"state": "none", "headline": "No second dataset for this variable yet",
                "detail": f"{info['name']} comes from one NASA dataset only, so it cannot be cross-checked yet."}
    try:
        from td.giovanni import GIOVANNI_VARIABLES, fetch_series_giovanni

        other = fetch_series_giovanni(other_id, bbox(list(land)), y0, y1)
        label = GIOVANNI_VARIABLES[other_id].get("label", other_id)
    except FetchError as exc:
        return {"state": "single", "headline": "Second dataset not reachable right now",
                "detail": f"The verdict above uses one dataset only. {exc}"}
    except Exception as exc:  # missing library, network, login: the verdict must still stand
        traceback.print_exc()
        return {"state": "single", "headline": "Second dataset not reachable right now",
                "detail": f"The verdict above uses one dataset only ({type(exc).__name__})."}

    primary = data[var_id].dropna()
    common = primary.index.intersection(other.index)
    if len(common) < 60:
        return {"state": "single", "headline": "Too little overlap to cross-check",
                "detail": f"{label} and {PRIMARY_LABEL} share only {len(common)} months for these years "
                          "(at least 60 are needed)."}
    a, b = primary.loc[common], other.loc[common]
    res_a, res_b = analyze(a, var_id), analyze(b, var_id)
    state = agreement(res_a, res_b)
    r = correlate(a, b)
    d, u = info.get("decimals", 2), info.get("units", "")
    span = f"{common[0].year}–{common[-1].year}"
    rate = lambda x: f"{x:+.{d}f} {u}".strip()  # noqa: E731
    word = lambda s: "rising" if s > 0 else "falling"  # noqa: E731
    name = info["name"].lower()
    if state == "agree":
        headline = "Two NASA datasets agree"
        detail = (f"Both show {name} {word(res_a['slope_decade'])} over {span}: "
                  f"{rate(res_a['slope_decade'])} per decade ({PRIMARY_LABEL}) and "
                  f"{rate(res_b['slope_decade'])} per decade ({label}).")
    elif state == "disagree":
        headline = "The two datasets disagree"
        detail = (f"Over {span}, {PRIMARY_LABEL} shows {name} {word(res_a['slope_decade'])} but {label} shows it "
                  f"{word(res_b['slope_decade'])}. Treat this verdict with caution.")
    else:
        headline = "The second dataset can't confirm this yet"
        detail = (f"Over {span}, the trend is {res_a['tier']} in {PRIMARY_LABEL} ({rate(res_a['slope_decade'])} per decade) "
                  f"and {res_b['tier']} in {label} ({rate(res_b['slope_decade'])} per decade). "
                  "Neither clearly confirms nor contradicts the other.")
    if r["r"] is not None:
        detail += f" Their month-to-month ups and downs move together (r = {r['r']:.2f})."
    return {
        "state": state, "headline": headline, "detail": detail, "note": INDEPENDENCE_NOTE.get(other_id, ""),
        "years": [int(common[0].year), int(common[-1].year)], "months": int(len(common)),
        "sources": [
            {"label": PRIMARY_LABEL, "slope_decade": num(res_a["slope_decade"]), "ci_decade": num(res_a["ci_decade"]),
             "tier": res_a["tier"]},
            {"label": label, "slope_decade": num(res_b["slope_decade"]), "ci_decade": num(res_b["ci_decade"]),
             "tier": res_b["tier"]},
        ],
        "r": num(r["r"]),
        "figure": cross_check_figure(a, b, "MERRA-2", label.split(" (")[0], u),
    }


# ------------------------------------------------------------------ quick scan + plain words (suggestions)

def _rate(v, info) -> str:
    d, u = info.get("decimals", 2), info.get("units", "")
    if " to " in u:  # a 0-to-1 index has no unit to print
        u = ""
    return f"{v:+.{d}f} {u}".strip()


def scan_data(data, y0, y1, var_ids=None) -> list[dict]:
    """Each variable tested on the same area: what is changing here? Each verdict is still tested in full."""
    out = []
    for vid, info in variables().items():
        if vid not in data or (var_ids is not None and vid not in var_ids):
            continue
        try:
            res = analyze(data[vid], vid)
        except Exception:  # e.g. a variable that is zero all year (no snow): nothing to scan
            continue
        out.append({"var_id": vid, "name": info["name"], "tier": res["tier"],
                    "direction": "rising" if res["slope_decade"] > 0 else "falling",
                    "rate_per_decade": _rate(res["slope_decade"], info), "years": f"{y0}–{y1}"})
    return out


def quick_scan(body) -> dict:
    body = {**body, "var_id": body.get("var_id") or next(iter(variables()))}
    pts, land, data, var_id, y0, y1, months = area_data(body)
    ranked = ranked_questions(pts, area_means(data))
    wanted = {q["primary"] for q in ranked["questions"]}
    return {"scan": scan_data(data, y0, y1, wanted), **ranked}


def explain_case(body) -> dict:
    """Facts the app computed -> plain-language summary and next questions (Gemini, or a template)."""
    from td.explain import explain

    pts, land, data, var_id, y0, y1, months = area_data(body)
    info = variables()[var_id]
    try:
        res = analyze(data[var_id], var_id)
    except ValueError as exc:
        raise FetchError(str(exc)) from None
    ranked = ranked_questions(pts, area_means(data))
    climate = ranked.get("climate") or {}
    facts = {
        "question_id": body.get("question_id"),
        "var_id": var_id,
        "place": f"{len(land)} land grid points picked on the map",
        "climate": climate.get("label", ""),
        "verdict": {
            "variable": info["name"], "headline": verdict(res)["headline"], "tier": res["tier"],
            "rate_per_decade": _rate(res["slope_decade"], info),
            "total_change": _rate(res["total_change"], info), "years": f"{y0}–{y1}",
        },
        "quick_scan": scan_data(data, y0, y1, {q["primary"] for q in ranked["questions"]}),
    }
    cc = body.get("cross")
    if isinstance(cc, dict) and cc.get("state") in ("agree", "disagree", "single"):
        facts["cross_check"] = {k: str(cc.get(k, ""))[:400] for k in ("state", "headline", "detail")}
    qs = {q["id"]: q for q in ranked["questions"]}   # in climate order: the fallback keeps it
    out = explain(facts, qs)
    out["next"] = [{"id": q, "label": qs[q]["label"]} for q in out["next"] if q in qs]
    return out


def run_analysis(body) -> dict:
    pts, land, data, var_id, y0, y1, months = area_data(body)
    vars_ = variables()
    series = data[var_id]
    try:
        res = analyze(series, var_id)
    except ValueError as exc:
        raise FetchError(str(exc)) from None
    words = verdict(res)

    link = None
    linked = body.get("linked")
    if linked and linked in data and linked != var_id:
        link = {"var_id": linked, "name": vars_.get(linked, {}).get("name", linked), "why": body.get("why", ""),
                **{k: num(v) for k, v in correlate(series, data[linked]).items()}}

    zones = None
    if len(land) >= 2:
        try:
            from td.trendmap import trend_grid

            grid = trend_grid({pt: df.reindex(months) for pt, df in land.items()}, var_id, fdr_alpha=0.10)
            zones = [{k: num(v) for k, v in row.items()} for row in grid.to_dict(orient="records")]
        except NotImplementedError:
            zones = None

    return {
        "var_id": var_id,
        "variable": vars_[var_id],
        "years": [y0, y1],
        "res": {k: num(v) for k, v in res.items() if not k.startswith("_")},
        "words": words,
        "points": [{"lat": lat, "lon": lon, "land": (lat, lon) in land} for lat, lon in pts],
        "points_used": len(land),
        "region_type": region_type(bbox(pts)),
        "link": link,
        "zones": zones,
        "figures": {"anomaly": figure_json(trend_figure(series, res, view="anomaly")),
                    "raw": figure_json(trend_figure(series, res, view="raw"))},
        "series": {"month": [d.strftime("%Y-%m") for d in series.index], "value": [num(v) for v in series]},
    }


# ------------------------------------------------------------------ HTTP

class Handler(BaseHTTPRequestHandler):
    server_version = "TrendDetective/1.0"

    def log_message(self, fmt, *args):  # quieter console: one line per API call
        if self.path.startswith("/api/"):
            sys.stderr.write("%s %s\n" % (self.command, self.path))

    def send_json(self, payload, status=200):
        raw = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(raw)

    def send_file(self, path: Path, ctype: str):
        raw = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def read_body(self) -> dict:
        n = int(self.headers.get("Content-Length") or 0)
        if n > 100_000:
            raise FetchError("Request too large.")
        try:
            return json.loads(self.rfile.read(n) or b"{}")
        except json.JSONDecodeError:
            raise FetchError("The request was not valid JSON.") from None

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path == "/api/meta":
            return self.send_json({"years": [config.FIRST_YEAR, config.LAST_YEAR], "max_points": MAX_POINTS,
                                   "min_years": MIN_YEARS, "variables": variables()})
        if path == "/vendor/plotly.min.js":
            return self.send_file(PLOTLY_JS, "text/javascript; charset=utf-8")
        name = "index.html" if path in ("/", "") else path.lstrip("/")
        target = (STATIC / name).resolve()
        if STATIC.resolve() not in target.parents or not target.is_file():
            return self.send_json({"error": "Not found"}, 404)
        types = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".css": "text/css"}
        return self.send_file(target, types.get(target.suffix, "application/octet-stream"))

    def do_POST(self):
        try:
            body = self.read_body()
            if self.path == "/api/area":
                return self.send_json(ranked_questions(clean_points(body.get("points")) if body.get("points") else []))
            if self.path == "/api/point":
                return self.send_json(point_summary(body))
            if self.path == "/api/analyze":
                return self.send_json(run_analysis(body))
            if self.path == "/api/crosscheck":
                return self.send_json(cross_check(body))
            if self.path == "/api/scan":
                return self.send_json(quick_scan(body))
            if self.path == "/api/explain":
                return self.send_json(explain_case(body))
            return self.send_json({"error": "Not found"}, 404)
        except FetchError as exc:
            return self.send_json({"error": str(exc)}, 400)
        except NotImplementedError:
            return self.send_json({"error": "Part of the pipeline is not merged into this branch yet."}, 501)
        except Exception:  # keep the server alive; details go to the console only
            traceback.print_exc()
            return self.send_json({"error": "Something went wrong on the server. Check the console."}, 500)


def main():
    httpd = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"Trend Detective web UI on http://localhost:{PORT}  (Ctrl+C to stop)")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
