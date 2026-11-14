# NASA Trend Detective

NASA Space Apps Challenge 2026 project ("Be An Earth System Trend Detective!"). Goal: pick an Earth science variable and a region, build a long time series, and test whether it is really changing (rate per decade, t-test with 95% confidence interval, Mann-Kendall with Sen's slope), including where it rises in one zone and falls in another.

The step-by-step plan, task split and full reference list are in `PLAN.md`. Read it before starting a task.

## Challenge objectives (every change must keep all four working)
1. Identify Earth science variables of interest that can be investigated for trends.
2. Acquire the data for a particular region.
3. Generate and visualize a time series long enough for statistical analysis.
4. Report the rate of change and test its significance (t-test, Mann-Kendall or confidence intervals).

Judging criteria: Impact, Creativity, Validity, Relevance, Presentation.

## Data
- Source: NASA POWER monthly point API (MERRA-2 reanalysis): `T2M`, `PRECTOTCORR`, `GWETTOP`, 1981 to 2025. No login.
- Second source for rain: GPM IMERG via Giovanni (Earthdata Login). Optional: MODIS NDVI via AppEEARS.
- Never commit large raw data files or API keys. Keys go in `.env` (gitignored, see `.env.example`); `data/cache/*.json` is gitignored.

## Tech stack
Python 3.12, Streamlit, Folium + streamlit-folium, Plotly, pandas/NumPy, statsmodels (OLS with Newey-West errors, Benjamini-Hochberg FDR), pymannkendall (Hamed-Rao, Sen's slope), requests, earthaccess + harmony-py (Giovanni), pytest. The team writes all code from an empty repo; architecture, file tree and contracts are in `PLAN.md`. Deployment (Docker, Cloud Run) is out of scope for now.

## Team & ownership (only the owner edits these files)
- R4Y3NN-k (A, data, repo owner, merges PRs): `td/fetch.py`, `td/cache.py`, `td/giovanni.py`, `td/appeears.py`, `scripts/`, `requirements*.txt`, `.gitignore`, `pytest.ini`
- [teammate 3] (B, stats): `td/analyze.py`, `td/trendmap.py`, `td/sample.py`, `tests/`
- yahya0X (C, dashboard): `app.py`, `td/charts.py`, `.streamlit/`
- [teammate 4] (D, content and story): `td/config.py`, `td/report.py`, `README.md`, `docs/`

Don't edit another person's area without saying so in the commit message. Changes to `analyze()` outputs need B's review.

## Contracts (fixed signatures; code against them)
```python
fetch_box(box, start_year, end_year) -> BoxData          # .data, .points, .point_data
sample_box_data(box) -> BoxData                          # fake data for building early
analyze(series, var_id) -> dict                          # slope_decade, ci_decade, p_ttest, p_mk, sen_decade, tier, ...
trend_grid(point_data, var_id, fdr_alpha=0.10) -> DataFrame
compare(sub_res, whole_res, sub_name, whole_name) -> str
agreement(res_a, res_b) -> "agree" | "disagree" | "single"
fetch_series_giovanni(var_id, box, start_year, end_year) -> pd.Series
trend_map_figure(grid_df, var_id) -> plotly Figure
```

## Working rules
- Small steps: one feature per task; commit after each working step with a clear message.
- Never push to main: branch `feat/<area>-<step>`, open a pull request; R4Y3NN-k merges after `python -m pytest -q` passes.
- Pull main before each step. Step 0 creates every file with its signatures; after that nobody creates a shared file. Build against `td/sample.py` until real code lands.
- Keep the README updated with how to install and run the project.
- Prefer simple, readable code over clever code; this is a hackathon demo.
- Ask before adding big new dependencies.
- Gates: MVP on real data Sat 21:00; feature freeze Sun 18:00 (bug fixes only after); submit by Sun 23:00 (deadline 23:59).

## Science rules
- A trend is "significant" only when both tests give p < 0.05 and agree in sign; "suggestive" when either gives p < 0.10.
- Zone maps use Benjamini-Hochberg FDR (alpha 0.10) across grid points.
- Say "consistent with", never "caused by". Correlation is not cause.
- Never put a number in the demo that the app didn't produce from real data.

## SI (AI) rules from the submission guide
- SI may speed up the work but must not come up with the idea of how to solve the challenge. Our concept comes from our own brainstorm documents.
- No NASA logos, flags or mission identifiers in any SI-generated content.
- SI-generated images and videos carry a visible "SI-generated" watermark.
- Acknowledge SI-assisted code in descriptive text and metadata: a header line in each AI-assisted file ("SI-assisted: parts of this file were drafted with Claude (Anthropic) and reviewed by the team"), the README "SI use" section, and the app footer.

## Key references
- NASA POWER API: https://power.larc.nasa.gov/docs/services/api/
- Giovanni configured variables: https://api.giovanni.earthdata.nasa.gov/configured-variables/
- GES DISC tutorials: https://github.com/nasa/gesdisc-tutorials
- AppEEARS: https://appeears.earthdatacloud.nasa.gov/
- pyMannKendall: https://github.com/mmhs013/pyMannKendall
- statsmodels multipletests: https://www.statsmodels.org/stable/generated/statsmodels.stats.multitest.multipletests.html
- Method: Acker et al. 2009 (SeaWiFS chlorophyll trends); Hamed and Rao 1998 (modified Mann-Kendall); Wilks 2016 (FDR for gridded data)
- Full list: `PLAN.md` → References
