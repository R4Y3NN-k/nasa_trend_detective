# Trend Detective

NASA Space Apps Challenge 2026: *Be An Earth System Trend Detective!* Pick a region and a question,
and test whether an Earth science variable is really changing, with NASA data from 1981 to 2025.

Status: step 0 skeleton (every file has its signatures; the code arrives in steps 1–4). See `PLAN.md`.

## Install and run

Python 3.12 or newer.

```bash
git clone https://github.com/R4Y3NN-k/nasa_trend_detective.git
cd nasa_trend_detective
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
python -m pytest -q
streamlit run app.py
```

## Data

NASA POWER monthly point API (MERRA-2 reanalysis): `T2M`, `PRECTOTCORR`, `GWETTOP`, 1981–2025, no login.
Keys for Earthdata services go in `.env` (see `.env.example`), never in git.
