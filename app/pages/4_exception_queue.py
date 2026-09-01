"""
FinControl AI - Exception Queue page (Module 10, page 4)
=============================================================
Every exception, filterable by type / decision / confidence / status, so
an operator can triage without scrolling the full reconciliation table.
"""

import os
import sys

import streamlit as st

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.common import get_investigations, require_data, simulated_banner  # noqa: E402
from database.db import get_transactions  # noqa: E402

st.set_page_config(page_title="Exception Queue – FinControl AI", page_icon="\U0001f4a0", layout="wide")
st.title("Exception Queue")
simulated_banner()

conn = require_data()
tx = get_transactions(conn)
investigations = get_investigations(conn)
conn.close()

queue = tx[tx["status"] == "EXCEPTION"].merge(
    investigations, on="transaction_id", how="left", suffixes=("", "_ai")
)
queue["decision"] = queue["decision"].fillna("NOT_YET_INVESTIGATED")
queue["ai_status"] = queue["ai_status"].fillna("PENDING")

col_f1, col_f2, col_f3 = st.columns(3)
with col_f1:
    types = sorted(queue["exception_type"].dropna().unique())
    type_filter = st.multiselect("Exception type", types, default=types)
with col_f2:
    decisions = sorted(queue["decision"].unique())
    decision_filter = st.multiselect("Decision", decisions, default=decisions)
with col_f3:
    min_conf, max_conf = st.slider("Confidence range", 0.0, 1.0, (0.0, 1.0), step=0.05)

filtered = queue[
    queue["exception_type"].isin(type_filter)
    & queue["decision"].isin(decision_filter)
    & (queue["confidence"].fillna(0).between(min_conf, max_conf) | queue["confidence"].isna())
]

st.caption(f"Showing {len(filtered)} of {len(queue)} exceptions")

display_cols = [
    "transaction_id", "exception_type", "difference", "ai_status",
    "confidence", "decision", "recommendation",
]
st.dataframe(
    filtered[display_cols].style.format({"difference": "{:.2f}", "confidence": "{:.0%}"}, na_rep="—"),
    width="stretch",
    hide_index=True,
    height=560,
)
st.caption("Open **Exception Investigation** and pick a transaction ID above to see the full trail and record a decision.")
