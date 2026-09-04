"""
FinControl AI - Audit Log page (Module 10, page 5)
=======================================================
The full timestamped trail from database/db.py: every write to
transactions, investigations, and human_decisions gets an audit_log row
here -- actor (system / AI / human), action, and the evidence reference.
"""

import os
import sys

import streamlit as st

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.common import apply_theme, require_data  # noqa: E402
from database.db import get_audit_log  # noqa: E402

st.set_page_config(page_title="Audit Log – FinControl AI", page_icon="\U0001f4a0", layout="wide")
apply_theme()
st.title("Audit Log")
st.caption("Every write to the database, timestamped — who (or what) did it, and why.")

conn = require_data()
audit = get_audit_log(conn)
conn.close()

if audit.empty:
    st.info("No audit entries yet.")
    st.stop()

with st.container(border=True):
    col_f1, col_f2 = st.columns(2)
    with col_f1:
        actors = sorted(audit["actor"].unique())
        actor_filter = st.multiselect("Actor", actors, default=actors)
    with col_f2:
        search = st.text_input("Search transaction ID", "")

filtered = audit[audit["actor"].isin(actor_filter)]
if search:
    filtered = filtered[filtered["transaction_id"].fillna("").str.contains(search, case=False)]

st.caption(f"Showing {len(filtered)} of {len(audit)} audit entries, newest first")

actor_icon = {"system": "⚙️", "AI": "\U0001f916", "human": "\U0001f9d1"}
display = filtered.copy()
display["actor"] = display["actor"].apply(lambda a: f"{actor_icon.get(a.split(' ')[0], '')} {a}")

st.dataframe(
    display[["timestamp", "actor", "action", "transaction_id", "evidence_ref", "details"]],
    width="stretch",
    hide_index=True,
    height=600,
)
