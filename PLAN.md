# Trend Detective: build plan

Repo R4Y3NN-k/nasa_trend_detective · NASA Space Apps 2026 · Sat 14 Nov 16:45 to Sun 15 Nov 23:00 · the team writes all code from an empty repo · deployment (Docker, Cloud Run) is out of scope for now

## Who owns what

| | Person | Role | Owns (only they edit these) | Branches | Also |
| --- | --- | --- | --- | --- | --- |
| A | **R4Y3NN-k** | Data | `td/fetch.py, td/cache.py, td/giovanni.py, td/appeears.py, scripts/, requirements*.txt, .gitignore` | `feat/data-*` | Repo owner: creates the skeleton, reviews and merges every pull request |
| B | **[teammate 3]** | Stats | `td/analyze.py, td/trendmap.py, td/sample.py, tests/` | `feat/stats-*` | Reviews any change to analyze() outputs |
| C | **yahya0X** | Dashboard | `app.py, td/charts.py, .streamlit/, web/` | `feat/ui-*` | Only person who edits app.py and web/ |
| D | **[teammate 4]** | Content and story | `td/config.py, td/report.py, README.md, docs/` | `feat/content-*` | Only person who edits config.py |

## Challenge objectives and how we meet them

1. Identify Earth science variables of interest that can be investigated for trends.
2. Acquire the data for a particular region (most trends are not global, though some are).
3. Generate and visualize a time series long enough for statistical analysis.
4. Perform a basic statistical analysis: rate of change over time, and the trend's significance (t-test, Mann-Kendall test or confidence intervals).

| Objective | How the app meets it |
| --- | --- |
| 1. Variables | Questions name their variables; a card per variable (definition, source, units, record, why chosen, caveat); Explore any variable (steps 3, 4) |
| 2. Region | Presets, governorates, a drawn box; land points averaged with cos(latitude) weights; zone map per grid point (steps 1, 5) |
| 3. Time series | 1981–2025 monthly, raw or anomalies, trend line and 95% band, record length shown (step 3) |
| 4. Statistics | OLS slope per decade with 95% CI and t-test (Newey-West), Mann-Kendall (Hamed-Rao) and Sen's slope, FDR across zones, verdict tiers, years to significance (steps 2, 5) |

Judging criteria: Impact, Creativity, Validity, Relevance, Presentation.

## Architecture

Data flows top to bottom; each box is one owner's file.

```text
User ──▶ web/ (map-first UI: full-screen map + right dashboard)         [C]
            │  static/: Leaflet map, freehand lasso or tap grid cells,
            │           questions ranked for the area, verdict panel
            │  server.py: JSON API (stdlib) /api/meta, /api/area,
            │             /api/point (real values per cell), /api/analyze
   (or) app.py (Streamlit, 3 screens; kept as a fallback)               [C]
            │  question or variable                ◀── td/config.py      [D]
            ▼
      td/fetch.py  fetch_box(box, y0, y1) -> BoxData                    [A]
            │  grid of points ─▶ NASA POWER monthly point API
            │  land mask (GWETTOP) ─▶ cos(lat)-weighted average
            │  td/cache.py: every API answer saved as JSON              [A]
            │  td/giovanni.py: every cross-check via Giovanni (IMERG,
            │  CHIRPS/FLDAS, AIRS, GLDAS); td/appeears.py: NDVI (MODIS,
            │  VIIRS cross-check)                                       [A]
            ▼
      td/analyze.py  analyze(series, var_id) -> dict                    [B]
            │  anomalies ─▶ OLS + Newey-West (t-test, 95% CI)
            │  Mann-Kendall (Hamed-Rao) + Sen ─▶ tier, years-to-sig
            │  agreement(main on overlap, each cross-check on overlap)
      td/trendmap.py trend_grid(point_data, var_id) -> DataFrame        [B]
            │  analyze() per grid point ─▶ Benjamini-Hochberg FDR
            ▼
      td/charts.py (Plotly figures) [C]   td/report.py (Markdown, CSV) [D]
```

## Data sources and cross-checks

Rule: **one main dataset per variable, plus independent NASA datasets to cross-check it.** Every variable gets at least one cross-check. The verdict always comes from the main dataset; the others only say whether independent sources see the same trend.

Checked on Sat 14 Nov against Giovanni's configured-variables list (867 variables) and NASA's CMR catalogue (time ranges below). Every cross-check except NDVI goes through Giovanni, i.e. the `td/giovanni.py` code A already wrote: **no new dependency**.

| Variable (main: NASA POWER / MERRA-2, 1981–2025, ½° × ⅝°) | Cross-check 1 (priority) | Cross-check 2 (if time) | Why they are independent enough |
| --- | --- | --- | --- |
| Rainfall `PRECTOTCORR` | **GPM IMERG Final** monthly V07, 0.1°, **1998-01 → 2025-09**. Giovanni `GPM_3IMERGM_07_precipitation` (mm/hr → mm/day ×24, already in giovanni.py) | **CHIRPS rain in FLDAS** monthly 0.1°, **1982 → now**, land 50°S–50°N. Giovanni `FLDAS_NOAH01_C_GL_M_001_Rainf_f_tavg` (kg m⁻² s⁻¹ → mm/day ×86400) | IMERG: satellite microwave + IR calibrated to gauges. CHIRPS: satellite IR + station gauges. MERRA-2 rain is a model output corrected with gauge data. |
| Air temperature `T2M` | **AIRS** surface air temperature, Aqua satellite, V7, 1°, **2002-09 → now**. Giovanni mean of `AIRS3STM_7_0_SurfAirTemp_A` and `…_D` (day and night passes; K → °C) | **GLDAS Noah 2.1** air temperature, 0.25°, **2000 → now**. Giovanni `GLDAS_NOAH025_M_2_1_Tair_f_inst` (K → °C) | AIRS is a satellite retrieval (MERRA-2 assimilates AIRS radiances, so partly linked: say so in the caveat). GLDAS 2.1 is driven by NOAA GDAS, a different system from MERRA-2. |
| Topsoil wetness `GWETTOP` | **GLDAS Noah 2.1** soil moisture 0–10 cm, 0.25°, **2000 → now**. Giovanni `GLDAS_NOAH025_M_2_1_SoilMoi0_10cm_inst` (kg/m²) | **FLDAS Noah** soil moisture 0–10 cm, 0.1°, **1982 → now**. Giovanni `FLDAS_NOAH01_C_GL_M_001_SoilMoi00_10cm_tavg` (m³/m³) | Different land model (Noah) and different rain input (GDAS/GPCP, CHIRPS) from MERRA-2. Units differ from GWETTOP (0–1), so compare **direction and % per decade**, never raw values. FLDAS shares MERRA-2 temperature/radiation input: partly linked. |
| Greenness NDVI (step 8, optional) | main: MODIS Terra `MOD13A3` V061 monthly 1 km, 2000-02 → now (AppEEARS) | cross-check: **VIIRS** `VNP13A3` V002 monthly 1 km, **2012 → now** (AppEEARS, same job type) | Different satellite and sensor. MODIS Aqua (`MYD13A3`) is the same sensor type, so it does not count as independent. |

Rejected after checking: TRMM 3B43 (ended 2019-12, replaced by IMERG), GPCP daily V3.3 (daily only in Giovanni, IMERG already covers it), FLDAS air temperature (it is MERRA-2's), GLDAS 2.0 (ends 2014), GRACE-DA soil moisture (weekly, 2003–), SMAP (2015–, too short), GISTEMP (needs new NetCDF dependencies; AIRS covers temperature through Giovanni).

Overlaps used for each check (the main series is cut to the same months): rain 1998–2025 (IMERG) and 1982–2025 (CHIRPS); temperature 2003–2025 (AIRS) and 2000–2025 (GLDAS); soil 2000–2025 (GLDAS) and 1982–2025 (FLDAS); NDVI 2012–2025. Every overlap is at least 10 years. A check whose overlap is shorter (user picked few years) shows "Single source for these years".

What we do and do not do with the data:

- **Never merge or splice datasets into one series.** Sources differ in grid, sensors, bias and start date; joining them creates a step at the join that the tests report as a trend.
- **No data augmentation or gap filling.** It adds months that were never observed, makes the record look longer and the p-values better than they are, and breaks the rule that every number on screen comes from real data.
- **Cleaning only:** fill value −999 → missing; month 13 (annual) dropped; missing months counted and shown; sea cells skipped (land mask); anomalies remove the seasons before any test.
- **Compare trends, not values.** Each source has its own bias, so averages differ; the question is whether the direction and size of change agree. Both series are analysed on the **same area and the same overlapping months** before `agreement()` is called.
- One `agreement()` per cross-check (main vs each source, each on its own overlap). The verdict card sums them up: "3 NASA sources agree", "2 of 3 NASA sources agree, 1 disagrees: treat with caution", or "Single source only" (also when a source is down, over quota or not logged in: the app never fails because of it). Each line lists the sources and their slopes per decade over the overlap.
- Giovanni has a monthly request quota: every answer is cached, demo areas are prefetched, and cross-check 2 is only requested when cross-check 1 succeeded.

## Repository structure

Step 0 creates all of this, empty, in one commit. The last column is the owner.

```text
nasa_trend_detective/
├── CLAUDE.md, PLAN.md             team rules and this plan
├── README.md                      install, run, method, SI use              D
├── requirements.txt               pinned runtime libraries                   A
├── requirements-dev.txt           -r requirements.txt + pytest               A
├── .gitignore, .env.example       ignore .venv, data/cache/*.json, .env      A
├── pytest.ini                     pythonpath = . ; testpaths = tests         A
├── .streamlit/config.toml         theme, headless                            C
├── app.py                         the 3 screens (Streamlit fallback)         C
├── web/
│   ├── server.py                  JSON API over td.* + static files (stdlib) C
│   └── static/                    index.html, app.js (Tailwind, Leaflet)     C
├── td/
│   ├── __init__.py                                                           A
│   ├── config.py                  VARIABLES, REGIONS, QUESTIONS, rules       D
│   ├── cache.py                   get/put JSON by key                        A
│   ├── fetch.py                   POWER client, grid, land mask, average     A
│   ├── giovanni.py                all Giovanni cross-checks (step 7)         A
│   ├── appeears.py                MODIS NDVI via AppEEARS (step 8)           A
│   ├── analyze.py                 stats engine + verdict words               B
│   ├── trendmap.py                per-point trends + FDR (step 5)            B
│   ├── sample.py                  synthetic data so C and D never wait       B
│   ├── charts.py                  Plotly figures                             C
│   └── report.py                  case report (Markdown) + CSV               D
├── scripts/prefetch_demo.py       warm the cache, print verdicts             A
├── tests/                         test_fetch, test_analyze, test_app         B (A adds test_fetch)
├── data/cache/                    cached API answers (gitignored)
└── docs/                          validation.md, demo_stories.md, appeears_tasks.md   D
```

## Tech stack

| Layer | Tool | Why |
| --- | --- | --- |
| Language | Python 3.12 | One language for the whole team |
| App and UI | web/: Python http.server (stdlib) + Tailwind CSS + Leaflet (CDN) + Plotly.js (bundled with plotly) | Full-screen map, freehand lasso, right-hand dashboard; no new Python dependency |
| Map tiles | OpenStreetMap HOT style | Same look as our uMap reference template |
| Fallback UI | streamlit, folium + streamlit-folium | The original 3-screen app.py, kept working |
| Charts and zone map | plotly | Interactive time series; scattergeo zone map |
| HTTP | requests | NASA POWER calls with timeout and retries |
| Tables | pandas, numpy | Monthly series, weighted averages |
| Statistics | statsmodels | OLS with Newey-West (HAC) errors; multipletests(method='fdr_bh') |
| Statistics | pymannkendall | hamed_rao_modification_test: p-value and Sen's slope |
| Cross-check sources | earthaccess, harmony-py (already in requirements) | Earthdata Login and Giovanni area-averaged monthly series for IMERG, CHIRPS/FLDAS, AIRS, GLDAS (step 7) |
| Tests | pytest + streamlit.testing.v1.AppTest | Known-trend tests and a full click-through without network |
| Parallel fetch | concurrent.futures.ThreadPoolExecutor (stdlib) | 4 points at a time, gentle on POWER |

Pin exact versions in requirements.txt once step 0 installs cleanly (`pip freeze`).

## Contracts

Fixed signatures. Everyone codes against these from minute one.

```python
# td/fetch.py  (A)
@dataclass
class BoxData:
    data: pd.DataFrame        # index: month start (DatetimeIndex); columns: variable ids ("T2M", ...)
    points_total: int         # grid points requested
    points_used: int          # land points averaged
    points: list              # [(lat, lon, is_land)]
    point_data: dict          # {(lat, lon): DataFrame like .data}, land points only
class FetchError(RuntimeError): ...            # message safe to show users
def fetch_box(box, start_year, end_year) -> BoxData       # box = (west, south, east, north)
def grid_points(box) -> list[tuple[float, float]]

def fetch_point(lat, lon, start_year, end_year) -> pd.DataFrame       # one cell, cached (used by web/)
def is_land(df) -> bool ; def area_mean(point_data) -> pd.DataFrame

# td/giovanni.py  (A) — every Giovanni cross-check, area-averaged monthly series in the main variable's units
def fetch_series_giovanni(var_id, box, start_year, end_year) -> pd.Series   # step 7
    # var_id in GIOVANNI_VARIABLES: "IMERG", "CHIRPS", "AIRS_T", "GLDAS_T", "GLDAS_SM", "FLDAS_SM"
    # spec per id: Giovanni variable(s) (AIRS: day + night averaged), native units, conversion
    #   (factor and offset: ×24, ×86400, K − 273.15), first and last available month
    # raises GiovanniError (a FetchError, user-safe message) when down / over quota / not logged in

# td/appeears.py  (A)
def load_ndvi(task_id) -> pd.Series                                         # step 8, MODIS or VIIRS task

# td/cache.py  (A)
def make_key(*parts) -> str ; def get(key) -> dict | None ; def put(key, data) -> None

# web/server.py  (C) — JSON API used by web/static/app.js
GET  /api/meta                                   -> {years, max_points, min_years, variables}
POST /api/area    {points: [[lat, lon], ...]}    -> {region_type, questions (ranked)}
POST /api/point   {lat, lon}                     -> {land, means{var}, months, first, last}
POST /api/analyze {points, var_id, linked, years}-> {res, words, figures, points, link, zones, cross}
    # cross = {summary: "agree"|"mixed"|"disagree"|"single", n_sources,
    #          checks: [{source, name, agreement, overlap: [y0, y1], slope_main, slope_cross, units} |
    #                   {source, name, agreement: "single", reason}]}

# td/analyze.py  (B)
def anomalies(series) -> pd.Series
def analyze(series, var_id) -> dict   # keys: var_id, start, end, n_months, missing_months, span_years, mean,
    # slope_decade, ci_decade (lo, hi), p_ttest, p_mk, sen_decade, tier ("significant"|"suggestive"|"none"),
    # tests_agree, total_change, pct_decade (None unless relative), years_to_significance, short_record,
    # _anomalies, _trend_line (Series for charts)
def verdict(res) -> {"headline": str, "detail": str}
def correlate(a, b) -> {"r": float | None, "n": int}
def compare(sub_res, whole_res, sub_name, whole_name) -> str          # step 6
def agreement(res_a, res_b) -> "agree" | "disagree" | "single"        # step 7; both analysed on the same overlap

# td/trendmap.py  (B)
def trend_grid(point_data, var_id, fdr_alpha=0.10) -> pd.DataFrame
    # columns: lat, lon, slope_decade, pct_decade, p_ttest, p_mk, q_fdr, significant

# td/sample.py  (B) — fake data for building before real data exists
def sample_series(var_id="T2M", slope_decade=0.3, years=45, seed=0) -> pd.Series
def sample_box_data(box) -> BoxData

# td/charts.py  (C)
def trend_figure(series, res, view="anomaly"|"raw") -> go.Figure
def trend_map_figure(grid_df, var_id) -> go.Figure                    # step 5
def box_figure(points, box) -> go.Figure

# td/config.py  (D)
VARIABLES[id] = {name, short, definition, source, power_param, units, record, relative, decimals, why, caveat,
                 fetcher ("power"|"giovanni"|"appeears"), cross_check (optional: LIST of cross-check
                 variable ids, in priority order), cross_only (optional, True: never offered as a main variable)}
    # contract change: cross_check was one id, now a list (agree in chat; app code accepts both)
REGIONS[id]   = {name, box, type ("arid"|"savanna"|"temperate"|"polar"), blurb, parent (optional)}
QUESTIONS[id] = {label, icon, primary, linked: {region_type: var_id, "default": var_id}, why_linked: {...}}
def classify_box(box) -> region type ; def linked_for(question_id, region_type) -> (var_id, why)
FIRST_YEAR = 1981 ; LAST_YEAR = 2025 ; MIN_SPACING_DEG = 0.5 ; MAX_POINTS = 30

# td/report.py  (D)
def markdown_report(case, res, words, linked=None) -> str ; def csv_bytes(series, res) -> bytes
```

## Rules so nobody overlaps

1. Each file has exactly one owner (table above). Need a change in someone else's file? Ask in the team chat or open an issue; the owner makes it.
2. Step 0 creates every file with its function signatures (bodies raise NotImplementedError). After that nobody creates a shared file, and everyone codes against the contracts.
3. Build against td/sample.py until real code lands: C and D never wait for A or B.
4. Never push to main. Pull main, branch feat/<area>-<step>, push, open a pull request; R4Y3NN-k merges after `python -m pytest -q` passes.
5. Contract signatures and dict keys are fixed. Changing one needs the agreement of everyone who uses it, in the chat, before the PR.
6. Gates: MVP on real data Sat 21:00; feature freeze Sun 18:00 (bug fixes only after); submit by Sun 23:00.

## Setup (everyone)

```bash
git clone https://github.com/R4Y3NN-k/nasa_trend_detective.git
cd nasa_trend_detective
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt                 # after step 0 is merged
git checkout -b feat/<area>-<step>
python -m web.server                                # map-first UI on http://localhost:8600
streamlit run app.py                                # fallback 3-screen UI
```

## Steps at a glance

| Step | When | Who | Goal |
| --- | --- | --- | --- |
| 0. Skeleton and contracts | Sat 16:45–17:30 | A (with all) | One commit that creates every folder and file, with signatures only, so four people can start without touching each other's files. |
| 1. Data layer on NASA POWER | Sat 17:30–20:00 | A | fetch_box() returns real, area-averaged monthly series for any land box. |
| 2. Stats engine | Sat 17:30–20:00 | B | analyze() turns any monthly series into a defensible verdict. |
| 3. Dashboard | Sat 17:30–20:30 | C | Three screens that reach a verdict in two clicks, built on sample data, then switched to real data. |
| 4. Content: catalog, regions, report | Sat 17:30–20:00 | D | Every variable, region and question explains itself in plain words. |
| G1. GATE: MVP on real data | Sat 21:00 | All | Merge steps 1–4; the Tunisia flow runs end to end on real NASA data on every laptop. This meets all four challenge objectives. |
| 5. Opposite-trends zone map | Sat 21:00 – Sun 00:00 | B, C | One map shows where a variable rises and where it falls inside the region: the challenge's key insight. |
| 6. Region-versus-region sentence | Sat 21:00 – Sun 00:00 | B, C, D | Say whether a sub-region changes faster than its parent region. |
| 3b. Map-first web UI | Sat 18:30–21:00 (done on `yahya`) | C | Full-screen map, lasso or tap NASA grid cells, real values per cell, dashboard on the right. |
| 7. Cross-check every variable | Sat 22:00 – Sun 14:00 | A, B, D, C | Every verdict says how many independent NASA sources agree. Order: rain (IMERG) → temperature (AIRS) → soil (GLDAS) → second checks (CHIRPS, GLDAS T, FLDAS SM). Whatever is not working at 14:00 stays "single source". |
| 8. NDVI greenness (optional) | Sun 09:00–13:00 | A, D | Add "Is the land greening or browning?" if the AppEEARS jobs finished. |
| 9. Validation, polish, SI disclosure | Sun 09:00–18:00 | All | Show the method matches NASA's own tools, and mark all SI-assisted work. |
| G2. GATE: feature freeze | Sun 18:00 | All | Only bug fixes after this point. |
| 10. Story and submission | Sun 18:00–23:00 | D, C, B | A clear demo and a complete submission before 23:00 (deadline 23:59). |

### Step 0: Skeleton and contracts

**Sat 16:45–17:30 · A (with all).** One commit that creates every folder and file, with signatures only, so four people can start without touching each other's files.

- [ ] **A** (R4Y3NN-k): Create the tree above. Every module gets its docstring and the function signatures from the Contracts section, bodies `raise NotImplementedError`.
- [ ] **A** (R4Y3NN-k): Add requirements.txt (streamlit, streamlit-folium, folium, plotly, pandas, numpy, scipy, statsmodels, pymannkendall, requests), requirements-dev.txt, .gitignore (.venv, __pycache__, data/cache/*.json, .env), .env.example, pytest.ini, CLAUDE.md, PLAN.md.
- [ ] **All** (All): 15-minute call: read the Contracts together and agree on them. Then everyone clones, installs and branches.

Contracts: All of them (see Contracts)

Tech stack: Git, GitHub, Python 3.12, venv, pip

Resources: This plan · CLAUDE.md

Done when: main has the skeleton; `pip install -r requirements-dev.txt` works on all four laptops.

### Step 1: Data layer on NASA POWER

**Sat 17:30–20:00 · A.** fetch_box() returns real, area-averaged monthly series for any land box.

- [ ] **A** (R4Y3NN-k): cache.py: key = sha1 of the request parts; read/write data/cache/<key>.json.
- [ ] **A** (R4Y3NN-k): fetch.py grid_points(): cell centres starting at 0.5° spacing, widening ×1.25 until at most 30 points (Tunisia ≈ 28).
- [ ] **A** (R4Y3NN-k): fetch.py one request per point: GET power.larc.nasa.gov/api/temporal/monthly/point with parameters=T2M,PRECTOTCORR,GWETTOP, community=AG, latitude, longitude, start=1981, end=2025, format=JSON; timeout 90 s, 3 retries, back off on HTTP 429; cache every answer.
- [ ] **A** (R4Y3NN-k): Parse properties.parameter.<NAME>: keys YYYYMM; skip month 13 (the annual value); fill value −999 → NaN.
- [ ] **A** (R4Y3NN-k): Land mask: a point whose GWETTOP is all missing is sea; skip it. Average land points month by month with cos(latitude) weights. Keep each land point's DataFrame in point_data. No land → FetchError with a clear message.
- [ ] **A** (R4Y3NN-k): 4 points in parallel (ThreadPoolExecutor). scripts/prefetch_demo.py: fetch every preset and print each variable's verdict. tests/test_fetch.py with a fake response in POWER's JSON shape (no network).

Contracts: fetch_box, grid_points, BoxData, FetchError; cache.get/put/make_key

Tech stack: requests, pandas, numpy, concurrent.futures

Resources: NASA POWER API docs · POWER data sources page (MERRA-2 ½° × ⅝°)

Done when: prefetch_demo.py prints real verdicts for Tunisia; data/cache shared with the team (zip it, it's gitignored).

### Step 2: Stats engine

**Sat 17:30–20:00 · B.** analyze() turns any monthly series into a defensible verdict.

- [ ] **B** ([teammate 3]): sample.py first (by 18:00, so C can build): sample_series() = seasonal cycle + known slope + noise; sample_box_data() builds a BoxData from it.
- [ ] **B** ([teammate 3]): anomalies(): value minus that calendar month's mean.
- [ ] **B** ([teammate 3]): OLS on anomalies vs decimal years: sm.OLS(...).fit(cov_type='HAC', cov_kwds={'maxlags': 12}) → slope, 95% CI, t-test p. Report per decade.
- [ ] **B** ([teammate 3]): pymannkendall.hamed_rao_modification_test(anomalies) → p and Sen's slope (per month step × 120 = per decade).
- [ ] **B** ([teammate 3]): Tiers: significant = both p < 0.05 and same sign; suggestive = either p < 0.10; else none. % per decade for relative variables. Years to significance: n_needed = n·(1.96/|t|)^(2/3), extra years = (n_needed − n)/12.
- [ ] **B** ([teammate 3]): verdict() words: "Air temperature rising about 0.30 °C per decade" / "possibly rising" / "No clear trend yet". correlate() = Pearson r of anomalies.
- [ ] **B** ([teammate 3]): tests/test_analyze.py: a series with slope 0.3/decade comes back as 0.3 ± 0.05 and significant; flat series rarely significant; missing months handled.

Contracts: analyze, anomalies, verdict, correlate; sample_series, sample_box_data

Tech stack: statsmodels, pymannkendall, numpy, pandas, pytest

Resources: Acker et al. 2009 (challenge Resources tab) · Hamed and Rao 1998 · pyMannKendall and statsmodels docs

Done when: Tests pass; on real Tunisia data the slope matches a hand check in a spreadsheet.

### Step 3: Dashboard

**Sat 17:30–20:30 · C.** Three screens that reach a verdict in two clicks, built on sample data, then switched to real data.

- [ ] **C** (yahya0X): app.py with st.session_state.step (1, 2, 3) and st.progress.
- [ ] **C** (yahya0X): Screen 1: st.radio of REGIONS + "Draw your own box"; folium map with a Rectangle for presets, Draw plugin (rectangle only) for custom; four number inputs to fine-tune; year slider 1981–2025; validate the box (west < east, south < north, 0.5° to 40° per side, at least 10 years).
- [ ] **C** (yahya0X): Screen 2: radio "Ask a question" / "Explore any variable"; captions show main and linked variables for the region type; "coming later" list.
- [ ] **C** (yahya0X): Screen 3: verdict card (st.info / st.warning / bordered container by tier), 4 st.metric (OLS trend + CI, t-test p, Mann-Kendall p, Sen's slope), chart with raw/anomaly toggle, record length, years-to-significance note, variable cards, linked-variable box with r and "not proof of cause", How it works, downloads, Back and New case.
- [ ] **C** (yahya0X): charts.py trend_figure(): anomalies + dashed trend + 95% band, or raw + 12-month mean; box_figure(): box outline, land and sea points. Cache fetch_box with @st.cache_data.
- [ ] **C** (yahya0X): Use sample_box_data() until A merges step 1, then switch to fetch_box() (one line).

Contracts: Uses fetch_box, analyze, verdict, correlate, config dicts, report functions; owns trend_figure, box_figure

Tech stack: streamlit, plotly, folium, streamlit-folium

Resources: Streamlit docs · Plotly Python docs · our mockups

Done when: Full Tunisia flow works on real data with no errors.

### Step 4: Content: catalog, regions, report

**Sat 17:30–20:00 · D.** Every variable, region and question explains itself in plain words.

- [ ] **D** ([teammate 4]): config.py VARIABLES for T2M, PRECTOTCORR, GWETTOP (definition, units, record, why chosen, caveat; relative=True for rain and soil wetness).
- [ ] **D** ([teammate 4]): REGIONS: Tunisia (7.5, 30.2, 11.6, 37.5), Northern Tunisia, Southern Tunisia, Nile Delta, Western Sahel; governorates with parent "tunisia" (approximate boxes, check on a map): Tunis (9.8, 36.5, 10.6, 37.1), Sfax (10.0, 34.3, 11.2, 35.2), Gafsa (8.0, 34.0, 9.6, 34.8), Tozeur (7.6, 33.6, 8.6, 34.3); Luanda and Namibe from Emna's test.
- [ ] **D** ([teammate 4]): QUESTIONS hotter / rain / drying with linked variables by region type; classify_box() by centre latitude; linked_for().
- [ ] **D** ([teammate 4]): report.py: markdown_report() (verdict, test table, variable, caveat, linked variable, method) and csv_bytes().
- [ ] **D** ([teammate 4]): Submit AppEEARS MODIS NDVI area jobs now (they queue for hours); task IDs in docs/appeears_tasks.md. README: install, run, method.

Contracts: VARIABLES, REGIONS, QUESTIONS, classify_box, linked_for; markdown_report, csv_bytes

Tech stack: Python dicts, Markdown

Resources: NASA POWER parameter definitions · AppEEARS (Earthdata Login) · the 5 judging criteria

Done when: Config reviewed against real verdicts; report downloads; AppEEARS jobs submitted.

### G1: GATE: MVP on real data

**Sat 21:00 · All.** Merge steps 1–4; the Tunisia flow runs end to end on real NASA data on every laptop. This meets all four challenge objectives.

- [ ] **A** (R4Y3NN-k): Merge in order: content, stats, data, ui. Fix conflicts with the owner on a call.
- [ ] **All** (All): Pull main, run `python -m pytest -q` and `streamlit run app.py`. D picks 2–3 demo stories from real verdicts (docs/demo_stories.md), including a "no clear trend yet" case.

Done when: If this slips, the night goes to fixing it, not to new features.

### Step 5: Opposite-trends zone map

**Sat 21:00 – Sun 00:00 · B, C.** One map shows where a variable rises and where it falls inside the region: the challenge's key insight.

- [ ] **B** ([teammate 3]): trend_grid(): analyze() on every land point in point_data; Benjamini-Hochberg FDR across points (multipletests(method='fdr_bh'), alpha 0.10); significant = q < 0.10 and both tests agree. tests/test_trendmap.py.
- [ ] **B** ([teammate 3]): If zones disagree while the box average says "no clear trend", add to the verdict detail: opposite trends can cancel in an average.
- [ ] **C** (yahya0X): trend_map_figure(): Plotly scattergeo, red rising, blue falling, a dot on significant points; build it against a fake grid_df until B merges.
- [ ] **C** (yahya0X): Show the map under the averaged chart (keep both) with one line explaining the dots.

Contracts: trend_grid(point_data, var_id, fdr_alpha=0.10); trend_map_figure(grid_df, var_id)

Tech stack: statsmodels.stats.multitest, plotly scattergeo

Resources: Wilks 2016 (FDR for gridded data) · Emna's doc (Luanda vs Namibe)

Done when: Northern vs Southern Tunisia contrast visible on one map; tests pass.

### Step 6: Region-versus-region sentence

**Sat 21:00 – Sun 00:00 · B, C, D.** Say whether a sub-region changes faster than its parent region.

- [ ] **B** ([teammate 3]): compare(): "Northern Tunisia is drying faster than Tunisia as a whole" only when the 95% CIs don't overlap; otherwise "at a similar rate".
- [ ] **D** ([teammate 4]): Make sure every governorate and sub-region preset has `parent`.
- [ ] **C** (yahya0X): When a preset has a parent, analyze both and show the sentence under the verdict.

Contracts: compare(sub_res, whole_res, sub_name, whole_name) -> str; REGIONS[id]['parent']

Tech stack: Same as step 2

Resources: None new

Done when: Sentence appears for Northern Tunisia, Southern Tunisia and each governorate.

### Step 7: Cross-check every variable

**Sat 22:00 – Sun 14:00 · A, B, D, C.** Every verdict says how many independent NASA sources agree. Sources, time ranges and Giovanni ids: see Data sources and cross-checks. Rules: no merging, compare trends on the same overlap, never fail because a source is down.

How it flows (one request, any variable):

1. The user picks cells and a question or variable; the verdict is computed on the POWER series over the chosen years, as today.
2. The server builds the cross-check box from the picked **land** cells (their bounding box plus half a cell; at least one cell of the coarsest source, i.e. 1° for AIRS).
3. For each id in `VARIABLES[var]['cross_check']` (priority order): `fetch_series_giovanni(id, box, max(y0, first_month), y1)`.
4. Overlap = months both series have. Fewer than 10 years → that check is "single" with the reason. Otherwise both are cut to it, each goes through `analyze()`, and `agreement(main_overlap, cross_overlap)` gives that check's result.
5. Summary over the checks: all "agree" → "N NASA sources agree"; any "disagree" → "Sources disagree, treat with caution" with the details; none available → "Single source only (reason)".
6. Cross-check 2 is only requested when cross-check 1 answered (protects the Giovanni quota). All answers are cached.

Order of work (each row is usable on its own; stop at 14:00 and keep what works):

| Order | Variable | Source | Owner of the new spec | Notes |
| --- | --- | --- | --- | --- |
| 7.1 | Rain | IMERG | A (done) | Already in giovanni.py, with tests |
| 7.2 | Temperature | AIRS (day + night mean) | A | Two Giovanni variables averaged; K → °C; 1° cells |
| 7.3 | Topsoil wetness | GLDAS 2.1 SoilMoi 0–10 cm | A | Units kg/m²: compare direction and % per decade only |
| 7.4 | Rain | CHIRPS (FLDAS) | A | ×86400 to mm/day; land 50°S–50°N only |
| 7.5 | Temperature | GLDAS 2.1 Tair | A | K → °C |
| 7.6 | Topsoil wetness | FLDAS SoilMoi 0–10 cm | A | m³/m³ |

Tasks:

- [x] **A** (R4Y3NN-k): giovanni.py fetch_series_giovanni() (merged in PR #7): GPM_3IMERGM_07 area average via harmony-py, mm/hr → mm/day (×24), month-start index, cached; GiovanniError is a FetchError; tests/test_giovanni.py (parser, units + cache, gives up after two failures, missing login). `.env.example` has the Earthdata names.
- [ ] **A** (R4Y3NN-k): Generalise `GIOVANNI_VARIABLES` specs: a list of Giovanni variables averaged together (AIRS day + night), conversion as factor **and** offset (K − 273.15), and the first/last available month so requests never ask outside the record. Add the specs 7.2 → 7.6 in that order; each with a test on a saved Giovanni CSV (no network).
- [ ] **A** (R4Y3NN-k): Run each new spec once for real with an Earthdata login on Tunisia and northern Tunisia; prefetch every cross-check for the demo boxes so the demo never depends on Giovanni being up. Check the quota endpoint before prefetching. If a source fails twice, drop it and tell the team.
- [ ] **D** ([teammate 4]): VARIABLES entries with `fetcher='giovanni'`, `cross_only=True`, name, units, record (from the Data sources table) and a caveat each: `IMERG` ("Rainfall, satellite (GPM IMERG)"), `CHIRPS` ("Rainfall, satellite + gauges (CHIRPS)"), `AIRS_T` ("Air temperature, satellite (AIRS)"; caveat: MERRA-2 uses AIRS data, so partly linked), `GLDAS_T`, `GLDAS_SM` and `FLDAS_SM` (caveat: different units, only the direction and % change are compared). Then `cross_check` lists: PRECTOTCORR → ["IMERG", "CHIRPS"], T2M → ["AIRS_T", "GLDAS_T"], GWETTOP → ["GLDAS_SM", "FLDAS_SM"].
- [ ] **D** ([teammate 4]): README setup: how to fill `.env` from `.env.example` for the cross-checks (optional; the app works without it). One sentence per variable card on what the cross-check is.
- [ ] **B** ([teammate 3]): agreement(res_a, res_b): "single" if res_b is None; "agree" = same sign and both at least suggestive; "disagree" = opposite signs with at least one significant; otherwise "single". Must not depend on units (sign and tier only). tests/test_analyze.py: agree, disagree, single, None, different units.
- [ ] **B** ([teammate 3]): Helper `overlap(a, b) -> (a_cut, b_cut)` in analyze.py (months where both are present), so web/ and app.py cut the same way; test it. `summarize_checks(results) -> "agree"|"mixed"|"disagree"|"single"`.
- [ ] **C** (yahya0X): web/server.py: in /api/analyze run steps 2–6 for every id in `cross_check` (accept a single id too) and return `cross` (see Contracts). Run after the main verdict; cache per (area, years, source) so a slow Giovanni delays a case at most once.
- [ ] **C** (yahya0X): Verdict panel: one summary line under the test lights ("3 NASA sources agree"), then one row per source: name, overlap years, its slope per decade (or % per decade when units differ) and agree / disagree / unavailable (reason). Evidence tab: each source's resolution and record. Same summary line in app.py.
- [ ] **C** (yahya0X): Tests: Giovanni unreachable (no login), one source down and one up, a short year range (overlap under 10 years). The app always answers.

Contracts: fetch_series_giovanni(var_id, box, start_year, end_year) -> pd.Series; agreement(res_a, res_b) -> str; overlap(a, b) -> (pd.Series, pd.Series); summarize_checks(list) -> str; VARIABLES[id]['cross_check'] -> list; /api/analyze `cross`

Tech stack: earthaccess, harmony-py, pandas (all already installed)

Resources: Giovanni configured-variables list and quota endpoint · NASA CMR collection pages for GPM_3IMERGM, FLDAS_NOAH01_C_GL_M, AIRS3STM, GLDAS_NOAH025_M · GES DISC Giovanni area-averaged notebook (April 2026) · Earthdata Login · Dezfuli et al. 2017 (IMERG over Africa) · Funk et al. 2015 (CHIRPS) · Rodell et al. 2004 (GLDAS) · McNally et al. 2017 (FLDAS)

Done when: for Tunisia and northern Tunisia, rain, temperature and topsoil wetness each show at least one cross-check line (7.1–7.3) in web/ and app.py; with no Earthdata login every line says "Single source only" and nothing breaks; tests pass. 7.4–7.6 are a bonus.

### Step 8: NDVI greenness (optional)

**Sun 09:00–13:00 · A, D.** Add "Is the land greening or browning?" if the AppEEARS jobs finished.

- [ ] **A** (R4Y3NN-k): appeears.py load_ndvi(task_id): download the finished CSV, monthly mean NDVI (0–1), cache. Works for MODIS `MOD13A3` (main) and VIIRS `VNP13A3` (cross-check) tasks.
- [ ] **D** ([teammate 4]): Submit a VIIRS `VNP13A3` area job next to each MODIS one (same areas); task ids in docs/appeears_tasks.md.
- [ ] **D** ([teammate 4]): NDVI variable (fetcher='appeears', cross_check ["VIIRS_NDVI"]) and question in config.py. The question appears on screen 2 automatically; the cross-check uses the step 7 path (overlap 2012–2025).

Contracts: load_ndvi(task_id) -> pd.Series

Tech stack: requests, pandas, AppEEARS API

Resources: NASA AppEEARS data resources notebooks

Done when: NDVI works for Tunisia, or the step is dropped at 13:00.

### Step 9: Validation, polish, SI disclosure

**Sun 09:00–18:00 · All.** Show the method matches NASA's own tools, and mark all SI-assisted work.

- [ ] **B** ([teammate 3]): Compare one result with Giovanni's own time-series plot for the same box; write it in docs/validation.md.
- [ ] **C** (yahya0X): UX fixes, loading and error messages; screenshots of each screen.
- [ ] **C** (yahya0X): Proposed (agree in chat): draw picked grid cells as squares at their native 0.5° × 0.625° size instead of dots, so the map shows what the data really is (gridded model cells, not stations); same squares for the zone map.
- [ ] **B** ([teammate 3]): docs/validation.md: a table per variable with the main and cross-check slopes per decade over each overlap, as the app produced them (Tunisia and northern Tunisia), and one sentence on any disagreement.
- [ ] **A** (R4Y3NN-k): Re-run prefetch for every preset and new variable; fix data gaps.
- [ ] **All** (All): Add the header line "SI-assisted: parts of this file were drafted with Claude (Anthropic) and reviewed by the team" to any of your files where you used an AI assistant.
- [ ] **D** ([teammate 4]): README "SI use" section and the project page draft (problem, solution, NASA data, method, SI use).

Contracts: No new contracts

Tech stack: Same as before

Resources: Giovanni web interface · Space Apps SI rules

Done when: Feature freeze at 18:00 with main green.

### G2: GATE: feature freeze

**Sun 18:00 · All.** Only bug fixes after this point.


### Step 10: Story and submission

**Sun 18:00–23:00 · D, C, B.** A clear demo and a complete submission before 23:00 (deadline 23:59).

- [ ] **C** (yahya0X): Screen recording of the best demo story.
- [ ] **B** ([teammate 3]): Fact-check every number in the video or slides against the app.
- [ ] **D** ([teammate 4]): Watermark any SI-generated image or video frame with "SI-generated" (screen recordings of the app need none). No NASA logos, flags or mission identifiers.
- [ ] **D** ([teammate 4]): 30-second video (English subtitles) or up to 7 slides including the title, at a public link. Answer the SI question (draft below). Tick Terms and Conditions and Confirm All Work is Original, then Submit for Judging.

Tech stack: Screen recorder, slides tool, Miro board

Resources: Space Apps submission page and rules

Done when: Submitted by 23:00.

## File ownership at a glance

| Path | Owner |
| --- | --- |
| `app.py, td/charts.py, .streamlit/, web/` | yahya0X (C) |
| `td/analyze.py, td/trendmap.py, td/sample.py, tests/` | [teammate 3] (B) |
| `td/fetch.py, td/cache.py, td/giovanni.py, td/appeears.py, scripts/` | R4Y3NN-k (A) |
| `requirements*.txt, .gitignore, .env.example, pytest.ini` | R4Y3NN-k (A) (ask before adding big dependencies) |
| `td/config.py, td/report.py, README.md, docs/` | [teammate 4] (D) |
| `CLAUDE.md, PLAN.md` | R4Y3NN-k (A) (changes agreed in the team chat) |

## Submission rules

- Deadline Sunday 15 Nov 23:59 local; we submit by 23:00.
- Demo: a video of up to 30 seconds or up to 7 slides including the title, hosted at a public link; everything in English (or English subtitles).
- Use at least one NASA dataset and name it (NASA POWER / MERRA-2; and where used: GPM IMERG, CHIRPS via FLDAS, AIRS, GLDAS via Giovanni; MODIS and VIIRS via AppEEARS).
- Tick Terms and Conditions and Confirm All Work is Original, then press Submit for Judging.

## SI (AI) rules

- SI tools (chatbots, LLMs, image generation) are allowed to speed up the work, but must not be used to come up with the idea of how to solve the challenge. Our concept comes from our own brainstorm documents (ideas PDF, Rayen's report, Emna's doc).
- No SI-generated content may use or modify NASA branding: no logos, flags or mission identifiers.
- Images and videos generated by SI carry a visible watermark.
- Code and data produced with SI are acknowledged in descriptive text and metadata (file headers, README "SI use" section, app footer).
- The SI question in the form is for data collection only; judges see the watermarks, headers and descriptions in the project itself.

Draft answer for the SI question in the form (edit so it's true for the team):

> Yes. We used Claude (Anthropic) as an assistant. The concept (a guided "detective" tool with opposite-trend zones, two statistical tests and a second data source) comes from our team's own brainstorm documents. We used Claude to compare and refine our options, draft our project plan, task split and architecture, and sketch UI mockups. [If used while coding: and to help write parts of the code, marked in file headers.] The team wrote, ran, tested and reviewed the code, and checked the statistics by hand against the raw data. All data comes from NASA sources; no data was generated by SI.

## References

- [NASA POWER API](https://power.larc.nasa.gov/docs/services/api/)
- [NASA POWER data sources (MERRA-2, CERES)](https://power.larc.nasa.gov/docs/methodology/data/sources/)
- [Giovanni configured variables](https://api.giovanni.earthdata.nasa.gov/configured-variables/)
- [Giovanni monthly quota](https://api.giovanni.earthdata.nasa.gov/quota)
- [GES DISC tutorials (Giovanni area-averaged time series notebook)](https://github.com/nasa/gesdisc-tutorials)
- [harmony-py](https://github.com/nasa/harmony-py)
- [earthaccess](https://github.com/nsidc/earthaccess)
- [Earthdata Login](https://urs.earthdata.nasa.gov/)
- [AppEEARS](https://appeears.earthdatacloud.nasa.gov/)
- [AppEEARS data resources (notebooks)](https://github.com/nasa/AppEEARS-Data-Resources)
- [pyMannKendall](https://github.com/mmhs013/pyMannKendall)
- [statsmodels OLS with robust (HAC) errors](https://www.statsmodels.org/stable/regression.html)
- [statsmodels multipletests (Benjamini-Hochberg)](https://www.statsmodels.org/stable/generated/statsmodels.stats.multitest.multipletests.html)
- [GPM IMERG](https://gpm.nasa.gov/data/imerg)
- [FLDAS (CHIRPS rain, soil moisture)](https://ldas.gsfc.nasa.gov/fldas)
- [GLDAS (air temperature, soil moisture)](https://ldas.gsfc.nasa.gov/gldas)
- [AIRS (surface air temperature)](https://airs.jpl.nasa.gov/)
- [NASA CMR collection search (time ranges checked there)](https://cmr.earthdata.nasa.gov/search/)
- [VIIRS vegetation indices VNP13A3](https://lpdaac.usgs.gov/products/vnp13a3v002/)
- [Leaflet](https://leafletjs.com/) · [Tailwind CSS](https://tailwindcss.com/) · [OpenStreetMap HOT tiles](https://www.hotosm.org/)
- [Streamlit docs](https://docs.streamlit.io)
- [streamlit-folium](https://github.com/randyzwitch/streamlit-folium)
- [Plotly Python](https://plotly.com/python/)
- [NASA Space Apps Challenge](https://www.spaceappschallenge.org/)
- Acker et al. 2009, SeaWiFS chlorophyll trends near river mouths (challenge Resources tab)
- Hamed and Rao 1998, modified Mann-Kendall test for autocorrelated data, Journal of Hydrology
- Funk et al. 2015, the climate hazards infrared precipitation with stations (CHIRPS), Scientific Data
- Rodell et al. 2004, the Global Land Data Assimilation System, Bulletin of the AMS
- McNally et al. 2017, a land data assimilation system for sub-Saharan Africa food and water security applications (FLDAS), Scientific Data
- Wilks 2016, field significance and FDR for gridded climate data, Bulletin of the AMS
- [Dezfuli et al. 2017, Validation of IMERG precipitation in Africa, Journal of Hydrometeorology](https://doi.org/10.1175/JHM-D-17-0139.1)

## Out of scope for now

Deployment (Dockerfile, Cloud Run, Cloud Storage cache, custom domain) is planned separately once the app works locally.
