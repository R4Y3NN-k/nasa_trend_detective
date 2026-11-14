# Trend Detective: step-by-step build plan

Repo R4Y3NN-k/nasa_trend_detective · NASA Space Apps 2026 · Sat 14 Nov 16:30 to Sun 15 Nov 23:00 · deployment (Docker, Cloud Run) is out of scope for now

## Who owns what

| | Person | Role | Owns (only they edit these) | Branches | Also |
| --- | --- | --- | --- | --- | --- |
| A | **R4Y3NN-k** | Data | `td/fetch.py, td/cache.py, td/giovanni.py, td/appeears.py, scripts/` | `feat/data-*` | Repo owner: reviews and merges every pull request |
| B | **[teammate 3]** | Stats | `td/analyze.py, td/trendmap.py, tests/` | `feat/stats-*` | Reviews any change to analyze() outputs |
| C | **yahya0X** | Dashboard | `app.py, td/charts.py, .streamlit/` | `feat/ui-*` | Only person who edits app.py |
| D | **[teammate 4]** | Content and story | `td/config.py, td/report.py, README.md, docs/` | `feat/content-*` | Only person who edits config.py |

## Challenge objectives and how we meet them

1. Identify Earth science variables of interest that can be investigated for trends.
2. Acquire the data for a particular region (most trends are not global, though some are).
3. Generate and visualize a time series long enough for statistical analysis.
4. Perform a basic statistical analysis: rate of change over time, and the trend's significance (t-test, Mann-Kendall test or confidence intervals).

| Objective | How the app meets it |
| --- | --- |
| 1. Variables | Questions name their variables; a card per variable (definition, source, units, record, why chosen, caveat); Explore any variable |
| 2. Region | Presets, governorates, a drawn box; land points averaged with cos(latitude) weights; zone map per grid point |
| 3. Time series | 1981–2025 monthly, raw or anomalies, trend line and 95% band, record length shown |
| 4. Statistics | OLS slope per decade with 95% CI and t-test (Newey-West), Mann-Kendall (Hamed-Rao) and Sen's slope, FDR across zones, verdict tiers, years to significance |

Judging criteria: Impact, Creativity, Validity, Relevance, Presentation.

## Rules so nobody overlaps

1. Each file has exactly one owner (table above). Need a change in someone else's file? Ask in the team chat; they make it.
2. New features go in new files that already exist as stubs (td/trendmap.py, td/giovanni.py, td/appeears.py), so nobody creates the same file twice.
3. Never push to main. Branch, push, open a pull request; R4Y3NN-k merges after `python -m pytest -q` passes.
4. Pull main before starting each step: `git checkout main && git pull && git checkout -b feat/<area>-<step>`.
5. Function signatures in the Contracts column are fixed. Code against them even before the other side is finished.
6. Feature freeze Sunday 18:00. After that, bug fixes only.

## Setup (everyone)

```bash
git clone https://github.com/R4Y3NN-k/nasa_trend_detective.git
cd nasa_trend_detective
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
python -m pytest -q                                 # 21 tests, offline
streamlit run app.py
```

## Steps

| Step | When | Who | Goal |
| --- | --- | --- | --- |
| 0. Bootstrap the repo | Sat 16:30–17:00 | A | Everyone starts from the same working code. |
| 1. Real data in | Sat 17:00–18:30 | A, D | The app shows real NASA verdicts for the 5 presets. |
| 2. Check the numbers | Sat 18:30–20:00 | B | Every number on screen is right before anything is built on it. |
| 3. Dashboard on real data | Sat 18:30–20:00 | C | A first-time user reaches a verdict in two clicks. |
| 4. Words and demo cases | Sat 18:30–20:00 | D | Every variable and region explains itself; demo stories picked from real results. |
| G1. GATE: MVP on real data | Sat 20:00 | All | Merge steps 1–4. The Tunisia flow runs end to end on real data on every laptop. |
| 5. Opposite-trends map | Sat 20:00–23:00 | B, C | One map shows where a variable rises and where it falls inside the region (the challenge's key idea). |
| 6. Region-versus-region sentence | Sat 20:00–23:00 | B, C, D | Say whether a sub-region changes faster than its parent region. |
| 7. Second NASA source for rain | Sat 21:00 – Sun 12:00 | A, B, D, C | Rain verdicts say "two sources agree", "sources disagree" or "single source only". |
| 8. NDVI (optional) | Sun 09:00–13:00 | A, D, C | Add "Is the land greening or browning?" if D's AppEEARS jobs finished. |
| 9. Validation and polish | Sun 09:00–18:00 | All | Show judges the method matches NASA's own tools. |
| G2. GATE: feature freeze | Sun 18:00 | All | Only bug fixes after this point. |
| 10. Story and submission | Sun 18:00–23:00 | D, C, B | A clear demo and a complete submission before 23:00 (deadline 23:59). |

### Step 0: Bootstrap the repo

**Sat 16:30–17:00 · A.** Everyone starts from the same working code.

- [ ] **A** (R4Y3NN-k): Unzip trend-detective.zip into the repo, commit as "Initial MVP", push to main.
- [ ] **A** (R4Y3NN-k): Protect main (Settings → Branches → require a pull request).
- [ ] **B C D** ([teammate 3], yahya0X, [teammate 4]): Clone, run the setup commands, confirm 21 tests pass and the app opens.

Contracts:

```python
None yet
```

Tech stack: Git, GitHub, Python 3.12, venv

Resources: README.md, CLAUDE.md in the repo

Done when: All four laptops run the app and the tests.

### Step 1: Real data in

**Sat 17:00–18:30 · A, D.** The app shows real NASA verdicts for the 5 presets.

- [ ] **A** (R4Y3NN-k): Run `python scripts/prefetch_demo.py` for all presets; note land points used and missing months; post the printed verdicts in the chat.
- [ ] **A** (R4Y3NN-k): Zip `data/cache/` and share it (it's gitignored) so B and C work on real data.
- [ ] **D** ([teammate 4]): Submit AppEEARS MODIS NDVI area jobs now for Tunisia, Nile Delta, Western Sahel (they queue for hours). Save the task IDs in docs/appeears_tasks.md.

Contracts:

```python
fetch_box(box, start_year, end_year) -> BoxData  (now also .point_data per land point)
```

Tech stack: requests, pandas, NASA POWER monthly point API (T2M, PRECTOTCORR, GWETTOP)

Resources: power.larc.nasa.gov/api/temporal/monthly/point · appeears.earthdatacloud.nasa.gov (Earthdata Login)

Done when: Cache shared; real verdicts in the chat by 18:30.

### Step 2: Check the numbers

**Sat 18:30–20:00 · B.** Every number on screen is right before anything is built on it.

- [ ] **B** ([teammate 3]): Hand-check Tunisia temperature: annual means in a spreadsheet, linear trend per decade should land close to the app's OLS slope.
- [ ] **B** ([teammate 3]): Confirm anomalies remove the seasons, tiers follow the rule (both tests p < 0.05 for significant), years-to-significance looks sensible.
- [ ] **B** ([teammate 3]): Review the wording in analyze.verdict(); fix anything that over-claims.

Contracts:

```python
analyze(series, var_id) -> dict  (keys unchanged)
```

Tech stack: statsmodels (OLS + Newey-West), pymannkendall (Hamed-Rao, Sen), pandas, a spreadsheet

Resources: Acker et al. SeaWiFS chlorophyll paper (method NASA used) · statsmodels and pymannkendall docs

Done when: Tunisia slope verified by hand; notes in docs/validation.md.

### Step 3: Dashboard on real data

**Sat 18:30–20:00 · C.** A first-time user reaches a verdict in two clicks.

- [ ] **C** (yahya0X): Run the app on A's real cache; click every flow (3 questions, Explore any variable, a drawn box, Back, New case).
- [ ] **C** (yahya0X): Polish screen 3: verdict first, readable metrics, chart toggle. Test drawing a box on a non-preset region.
- [ ] **C** (yahya0X): List bugs in other people's files as GitHub issues assigned to the owner, not as edits.

Contracts:

```python
Uses only fetch_box, analyze, verdict, correlate, trend_figure
```

Tech stack: Streamlit, Plotly, Folium + streamlit-folium

Resources: docs.streamlit.io · plotly.com/python · the mockups from our planning chat

Done when: Full Tunisia flow works locally on real data.

### Step 4: Words and demo cases

**Sat 18:30–20:00 · D.** Every variable and region explains itself; demo stories picked from real results.

- [ ] **D** ([teammate 4]): Review every text in config.py (definitions, why chosen, caveats) against the real verdicts A posted.
- [ ] **D** ([teammate 4]): Add governorate presets with `parent: "tunisia"` (approximate boxes, check on a map): Tunis (9.8, 36.5, 10.6, 37.1), Sfax (10.0, 34.3, 11.2, 35.2), Gafsa (8.0, 34.0, 9.6, 34.8), Tozeur (7.6, 33.6, 8.6, 34.3). Small boxes hold only 1–2 POWER points; say so in the blurb.
- [ ] **D** ([teammate 4]): Add Luanda and Namibe (Angola) presets from Emna's test; A runs prefetch for them and B checks the verdicts before anyone quotes them.
- [ ] **D** ([teammate 4]): Pick 2–3 demo stories, including one "no clear trend yet" case. Write them in docs/demo_stories.md.

Contracts:

```python
REGIONS, VARIABLES, QUESTIONS dicts in config.py (keys unchanged)
```

Tech stack: Python dicts, Markdown

Resources: The 5 judging criteria: Impact, Creativity, Validity, Relevance, Presentation

Done when: Config text reviewed; demo stories written.

### G1: GATE: MVP on real data

**Sat 20:00 · All.** Merge steps 1–4. The Tunisia flow runs end to end on real data on every laptop.

- [ ] **A** (R4Y3NN-k): Merge the four pull requests in order: content, stats, ui, data.
- [ ] **All** (All): Pull main, run the tests and the app.

Done when: If this slips, the evening goes to fixing it, not to new features.

### Step 5: Opposite-trends map

**Sat 20:00–23:00 · B, C.** One map shows where a variable rises and where it falls inside the region (the challenge's key idea).

- [ ] **B** ([teammate 3]): Implement trend_grid() in td/trendmap.py: analyze() per land point, Benjamini-Hochberg FDR across points (alpha 0.10), significant = q < 0.10 and both tests agree. Add tests/test_trendmap.py.
- [ ] **C** (yahya0X): Add trend_map_figure(grid_df, var_id) in td/charts.py: red rising, blue falling, a dot on significant points. Code it against a fake grid_df until B merges.
- [ ] **C** (yahya0X): Show the map on screen 3 under the averaged chart (keep both: the chart meets objective 3, the map shows opposite trends), with one line explaining the dots.
- [ ] **B** ([teammate 3]): When zones disagree and the box average says "no clear trend", add that to the verdict detail: opposite trends can cancel in an average.

Contracts:

```python
trend_grid(point_data, var_id, fdr_alpha=0.10) -> DataFrame[lat, lon, slope_decade, pct_decade, p_ttest, p_mk, q_fdr, significant]
trend_map_figure(grid_df, var_id) -> plotly Figure
```

Tech stack: statsmodels.stats.multitest.multipletests(method='fdr_bh'), Plotly scattergeo

Resources: Wilks (2016) on FDR for climate fields · our teammate's doc (opposite trends, Luanda vs Namibe)

Done when: Northern vs Southern Tunisia show on one map; tests pass.

### Step 6: Region-versus-region sentence

**Sat 20:00–23:00 · B, C, D.** Say whether a sub-region changes faster than its parent region.

- [ ] **B** ([teammate 3]): Add compare(sub_res, whole_res, sub_name, whole_name) -> str in td/analyze.py, for example "Northern Tunisia is drying faster than Tunisia as a whole". Only claim faster or slower when the CIs don't overlap; otherwise say "at a similar rate".
- [ ] **D** ([teammate 4]): Add a `parent` key to child presets in config.py (tunisia_north and tunisia_south → tunisia).
- [ ] **C** (yahya0X): When a preset has a parent, run both and show the sentence under the verdict.

Contracts:

```python
compare(sub_res, whole_res, sub_name, whole_name) -> str
REGIONS[id]['parent'] -> region id (optional key)
```

Tech stack: Same as step 2

Resources: None new

Done when: Sentence shows for Northern and Southern Tunisia.

### Step 7: Second NASA source for rain

**Sat 21:00 – Sun 12:00 · A, B, D, C.** Rain verdicts say "two sources agree", "sources disagree" or "single source only".

- [ ] **A** (R4Y3NN-k): Implement fetch_series_giovanni() in td/giovanni.py for GPM IMERG monthly precipitation (harmony-py, average='area'). Cache every result. If Giovanni fails twice, stop and tell the team.
- [ ] **D** ([teammate 4]): Add an IMERG entry to VARIABLES in config.py with fetcher='giovanni' and a `cross_check` key on PRECTOTCORR pointing to it.
- [ ] **B** ([teammate 3]): Add agreement(res_a, res_b) -> 'agree' | 'disagree' | 'single' in td/analyze.py (agree = same sign and both at least suggestive).
- [ ] **C** (yahya0X): Show the agreement line in the verdict card.

Contracts:

```python
fetch_series_giovanni(var_id, box, start_year, end_year) -> pd.Series
agreement(res_a, res_b) -> str
VARIABLES[id]['cross_check'] -> variable id (optional key)
```

Tech stack: earthaccess, harmony-py, pandas

Resources: Giovanni configured-variables list and quota endpoint · NASA gesdisc-tutorials notebook on Giovanni area-averaged time series (April 2026) · Earthdata Login

Done when: Tunisia rain shows an agreement line; the app still works if Giovanni is down.

### Step 8: NDVI (optional)

**Sun 09:00–13:00 · A, D, C.** Add "Is the land greening or browning?" if D's AppEEARS jobs finished.

- [ ] **A** (R4Y3NN-k): Implement load_ndvi(task_id) in td/appeears.py from the finished jobs; cache the series.
- [ ] **D** ([teammate 4]): Add the NDVI variable and question to config.py.
- [ ] **C** (yahya0X): Nothing new: the question appears on screen 2 automatically.

Contracts:

```python
load_ndvi(task_id) -> pd.Series (monthly, 0–1)
```

Tech stack: requests, pandas, AppEEARS API

Resources: NASA appeears-data-resources notebooks

Done when: NDVI question works for Tunisia, or the step is dropped by 13:00.

### Step 9: Validation and polish

**Sun 09:00–18:00 · All.** Show judges the method matches NASA's own tools.

- [ ] **B** ([teammate 3]): Compare one result with Giovanni's own time-series plot for the same box; write it in docs/validation.md.
- [ ] **C** (yahya0X): UX fixes, loading messages, clear error messages; screenshots of each screen.
- [ ] **D** ([teammate 4]): Draft the project page (problem, solution, NASA data used, method, AI disclosure).
- [ ] **A** (R4Y3NN-k): Re-run prefetch for every preset and new variable; fix data gaps.
- [ ] **All** (All): SI disclosure in your own files: keep or add the header line "SI-assisted: parts of this file were drafted with Claude (Anthropic) and reviewed by the team".
- [ ] **D** ([teammate 4]): Add an "SI use" section to README.md: what was AI-assisted (planning, first code draft, mockups), what the team did (review, tests, hand-checks, changes), and that all data is NASA data.

Contracts:

```python
No new contracts
```

Tech stack: Same as before

Resources: Giovanni web interface · our planning docs

Done when: Freeze at 18:00 with main green.

### G2: GATE: feature freeze

**Sun 18:00 · All.** Only bug fixes after this point.


### Step 10: Story and submission

**Sun 18:00–23:00 · D, C, B.** A clear demo and a complete submission before 23:00 (deadline 23:59).

- [ ] **C** (yahya0X): Screen recording of the best demo story.
- [ ] **B** ([teammate 3]): Fact-check every number in the video or slides against the app.
- [ ] **D** ([teammate 4]): Watermark any SI-generated image or video frame (mockups, diagrams) with "SI-generated". Screen recordings of the running app need no watermark. No NASA logos, flags or mission identifiers anywhere.
- [ ] **D** ([teammate 4]): Answer the SI question in the submission form (draft in PLAN.md, edit so it's true).
- [ ] **D** ([teammate 4]): 30-second video (English subtitles) or up to 7 slides including the title, at a public link. Fill every project field, disclose AI use, no NASA logo. Tick Terms and Conditions and Confirm All Work is Original, then Submit for Judging.

Tech stack: Screen recorder, slides tool, Miro board

Resources: Space Apps submission page and rules

Done when: Submitted by 23:00.

## File ownership at a glance

| Path | Owner |
| --- | --- |
| `app.py` | C (yahya0X) |
| `td/charts.py` | C (yahya0X) |
| `td/analyze.py` | B ([teammate 3]) |
| `td/trendmap.py` | B ([teammate 3]) |
| `tests/` | B ([teammate 3]) |
| `td/fetch.py` | A (R4Y3NN-k) |
| `td/cache.py` | A (R4Y3NN-k) |
| `td/giovanni.py` | A (R4Y3NN-k) |
| `td/appeears.py` | A (R4Y3NN-k) |
| `scripts/` | A (R4Y3NN-k) |
| `td/config.py` | D ([teammate 4]) |
| `td/report.py` | D ([teammate 4]) |
| `README.md, docs/` | D ([teammate 4]) |
| `requirements.txt` | A (ask before adding big dependencies) (R4Y3NN-k) |

## Submission rules

- Deadline Sunday 15 Nov 23:59 local; we submit by 23:00.
- Demo: a video of up to 30 seconds or up to 7 slides including the title, hosted at a public link; everything in English (or English subtitles).
- Use at least one NASA dataset and name it (NASA POWER / MERRA-2; Giovanni and AppEEARS where used).
- Tick Terms and Conditions and Confirm All Work is Original, then press Submit for Judging.

## SI (AI) rules

- SI tools (chatbots, LLMs, image generation) are allowed to speed up the work, but must not be used to come up with the idea of how to solve the challenge. Our concept comes from our own brainstorm documents (ideas PDF, Rayen's report, Emna's doc).
- No SI-generated content may use or modify NASA branding: no logos, flags or mission identifiers.
- Images and videos generated by SI carry a visible watermark.
- Code and data produced with SI are acknowledged in descriptive text and metadata (file headers, README "SI use" section, app footer).
- The SI question in the form is for data collection only; judges see the watermarks, headers and descriptions in the project itself.

Draft answer for the SI question in the form (edit so it's true for the team):

> Yes. We used Claude (Anthropic) as an assistant. The concept (a guided "detective" tool with opposite-trend zones, two statistical tests and a second data source) comes from our team's own brainstorm documents. We used Claude to compare and refine our options, draft our project plan and task split, write a first version of the app code (Streamlit interface, NASA POWER data fetcher, statistics module and tests) and sketch UI mockups. The team reviewed, ran, tested and changed all code, and checked the statistics by hand against the raw data. All data comes from NASA sources; no data was generated by SI. AI-assisted files are marked in their headers and in the README.

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
- [statsmodels multipletests (Benjamini-Hochberg)](https://www.statsmodels.org/stable/generated/statsmodels.stats.multitest.multipletests.html)
- [Streamlit docs](https://docs.streamlit.io)
- [Plotly Python](https://plotly.com/python/)
- [NASA Space Apps Challenge](https://www.spaceappschallenge.org/)
- Acker et al. 2009, SeaWiFS chlorophyll trends near river mouths (challenge Resources tab)
- Hamed and Rao 1998, modified Mann-Kendall test for autocorrelated data, Journal of Hydrology
- Wilks 2016, field significance and FDR for gridded climate data, Bulletin of the AMS
- [Dezfuli et al. 2017, Validation of IMERG precipitation in Africa, Journal of Hydrometeorology](https://doi.org/10.1175/JHM-D-17-0139.1)

## Out of scope for now

Deployment (Dockerfile, Cloud Run, Cloud Storage cache, custom domain) stays in the repo untouched and is planned separately.
