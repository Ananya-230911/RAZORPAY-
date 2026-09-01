"""
FinControl AI - Dashboard shared utilities
=============================================
Common helpers used by dashboard.py and every page in app/pages/.
Centralizes the DB connection, results.json loading, and the SIMULATED-mode
banner so all pages behave identically. Every page imports from here rather
than duplicating this logic.
"""

import json
import os
import sys

import streamlit as st

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from database.db import (  # noqa: E402
    DEFAULT_DB_PATH,
    get_audit_log,
    get_connection,
    get_full_case,
    get_human_decisions,
    get_investigations,
    get_transactions,
    record_human_decision,
)
from evaluation.evaluate import RESULTS_PATH  # noqa: E402


def get_conn():
    """A fresh connection to fincontrol.db, or None if the pipeline hasn't been run yet."""
    if not os.path.exists(DEFAULT_DB_PATH):
        return None
    return get_connection(DEFAULT_DB_PATH)


def require_data():
    """
    Common guard for every page: if fincontrol.db doesn't exist yet, explain
    how to fix it and stop rendering the rest of the page -- never show a
    page full of confusing empty tables or stack traces.
    """
    conn = get_conn()
    if conn is None:
        st.error(
            "No data yet — `fincontrol.db` doesn't exist. Run the pipeline first, "
            "from a terminal in the project root:"
        )
        st.code("python run.py --skip-dashboard --seed 42", language="bash")
        st.caption("Then reload this page (no need to restart the dashboard).")
        st.stop()
    return conn


def load_results():
    """evaluation/results.json, or None if evaluate.py hasn't been run yet."""
    if not os.path.exists(RESULTS_PATH):
        return None
    with open(RESULTS_PATH) as f:
        return json.load(f)


def simulated_banner():
    st.warning(
        "**SIMULATED / TEST MODE** — nothing on this dashboard moves real money or calls "
        "Razorpay. Every action here (Approve / Reject / Mark Unresolved) is written to the "
        "local database only, for demo purposes.",
        icon="⚠️",
    )


DECISION_COLORS = {
    "AUTO_SUGGESTED": "🟢",
    "NEEDS_HUMAN_REVIEW": "🟡",
}

STATUS_COLORS = {
    "MATCHED": "🟢",
    "EXCEPTION": "🟠",
}
