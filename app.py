# SI-assisted: parts of this file were drafted with Claude (Anthropic) and reviewed by the team
"""Trend Detective dashboard: 3 screens. Owner: C (dashboard). Step 3.

    streamlit run app.py

Screen 1: region (preset / drawn box) + years.  Screen 2: question or variable.
Screen 3: verdict, chart, map, cards, report.
Build against td.sample.sample_box_data() until td.fetch.fetch_box() lands.
"""
import streamlit as st

st.set_page_config(page_title="Trend Detective", page_icon="🔎", layout="wide")
st.title("Trend Detective")
st.info("Skeleton (step 0). The three screens arrive in step 3.")
