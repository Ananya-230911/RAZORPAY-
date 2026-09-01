"""
FinControl AI - Reconciliation Table page (Module 10, page 2)
==================================================================
Every transaction Module 2 (matcher.py) + Module 3 (classifier.py)
produced: status, amounts, and the difference. Straight from fincontrol.db.
"""

import os
import sys

import streamlit as st

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.common import require_data, simulated_banner  # noqa: E402
from database.db import get_transactions  # noqa: E402

st.set_page_config(page_title="Reconciliation – FinControl AI", page_icon="\U0001f4a0", layout="wide")
st.title("Reconciliation Table")
simulated_banner()

conn = require_data()
tx = get_transactions(conn)
conn.close()

col_f1, col_f2, col_f3 = st.columns(3)
with col_f1:
    status_filter = st.multiselect("Status", sorted(tx["status"].unique()), default=list(tx["status"].unique()))
with col_f2:
    exc_types = sorted(tx.loc[tx["exception_type"].notna(), "exception_type"].unique())
    type_filter = st.multiselect("Exception type", exc_types, default=exc_types)
with col_f3:
    search = st.text_input("Search transaction ID", "")

filtered = tx[tx["status"].isin(status_filter)]
filtered = filtered[filtered["exception_type"].isin(type_filter) | (filtered["status"] == "MATCHED")]
if search:
    filtered = filtered[filtered["transaction_id"].str.contains(search, case=False, na=False)]

st.caption(f"Showing {len(filtered)} of {len(tx)} transactions")

display_cols = [
    "transaction_id", "status", "exception_type", "payment_amt", "invoice_amt",
    "settlement_amt", "difference", "records_present", "date_gap_days", "is_duplicate", "merchant",
]
st.dataframe(
    filtered[display_cols].style.format({
        "payment_amt": "{:.2f}", "invoice_amt": "{:.2f}",
        "settlement_amt": "{:.2f}", "difference": "{:.2f}",
    }, na_rep="—"),
    width="stretch",
    hide_index=True,
    height=560,
)
