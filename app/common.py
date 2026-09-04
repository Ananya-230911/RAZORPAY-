"""
FinControl AI - Dashboard shared utilities
=============================================
Common helpers used by dashboard.py and every page in app/pages/.
Centralizes the DB connection, results.json loading, and the shared dark
theme / styling helpers so all 6 pages look and behave identically. Every
page imports from here rather than duplicating this logic.
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


# ---------------------------------------------------------------------------
# Theme / styling
# ---------------------------------------------------------------------------
# Palette mirrors .streamlit/config.toml -- kept here too so inline HTML
# (badges, card borders) uses the exact same hex values as the configured
# theme rather than drifting out of sync with it.
BG = "#0a0e17"
SURFACE = "#111827"
SURFACE_BORDER = "#1f2937"
ACCENT = "#3b82f6"
TEXT = "#e5e7eb"
TEXT_MUTED = "#9ca3af"

GOOD = "#22c55e"       # MATCHED / RESOLVED / AUTO_SUGGESTED
GOOD_BG = "#14291d"
WARN = "#f59e0b"        # EXCEPTION / NEEDS_HUMAN_REVIEW
WARN_BG = "#2b2210"
BAD = "#ef4444"          # UNRESOLVED
BAD_BG = "#2b1616"

STATUS_ICON = {"MATCHED": "✅", "EXCEPTION": "⚠️"}
AI_STATUS_ICON = {"RESOLVED": "✅", "UNRESOLVED": "❓", "PENDING": "⏳"}
DECISION_ICON = {"AUTO_SUGGESTED": "🟢", "NEEDS_HUMAN_REVIEW": "🟡", "NOT_YET_INVESTIGATED": "⏳"}

# Kept for any external caller expecting the old names.
STATUS_COLORS = STATUS_ICON
DECISION_COLORS = DECISION_ICON


def apply_theme():
    """
    Site-wide dark styling: typography, spacing, card containers, badges.
    Call once near the top of every page, right after st.set_page_config().
    Layered on top of .streamlit/config.toml's base dark palette -- the
    config sets Streamlit's own widget colors, this adds the layout/type
    polish Streamlit's theming API doesn't reach (headings, spacing, badges).
    """
    st.markdown(
        f"""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

        html, body, [class*="css"] {{
            font-family: 'Inter', system-ui, -apple-system, sans-serif;
        }}

        .block-container {{
            padding-top: 2rem;
            padding-bottom: 3rem;
            max-width: 1200px;
        }}

        h1 {{
            font-weight: 800 !important;
            font-size: 2.1rem !important;
            letter-spacing: -0.02em;
            margin-bottom: 0.3rem !important;
        }}
        h2 {{
            font-weight: 700 !important;
            font-size: 1.35rem !important;
            margin-top: 1.8rem !important;
            margin-bottom: 0.6rem !important;
        }}
        h3 {{
            font-weight: 600 !important;
            font-size: 1.05rem !important;
            color: {TEXT} !important;
        }}
        p, li, label, .stMarkdown {{
            color: {TEXT};
        }}
        .stCaption, [data-testid="stCaptionContainer"] {{
            color: {TEXT_MUTED} !important;
        }}

        /* Metric cards */
        [data-testid="stMetric"] {{
            background: {SURFACE};
            border: 1px solid {SURFACE_BORDER};
            border-radius: 12px;
            padding: 1rem 1.1rem;
            box-shadow: 0 1px 3px rgba(0,0,0,0.4);
        }}
        [data-testid="stMetricLabel"] {{
            color: {TEXT_MUTED} !important;
            font-weight: 500 !important;
        }}
        [data-testid="stMetricValue"],
        [data-testid="stMetricValue"] > div,
        [data-testid="stMetricValue"] * {{
            color: {TEXT} !important;
            font-weight: 700 !important;
            font-size: 1.4rem !important;
            white-space: normal !important;
            overflow: visible !important;
            text-overflow: unset !important;
            overflow-wrap: break-word;
            line-height: 1.3 !important;
        }}

        /* Bordered containers (st.container(border=True)) */
        [data-testid="stVerticalBlockBorderWrapper"] {{
            background: {SURFACE};
            border-color: {SURFACE_BORDER} !important;
            border-radius: 12px;
        }}

        /* Sidebar */
        [data-testid="stSidebar"] {{
            background: #0d1320;
            border-right: 1px solid {SURFACE_BORDER};
        }}
        [data-testid="stSidebarNav"] a {{
            border-radius: 8px;
        }}
        [data-testid="stSidebarNav"] a[aria-current="page"] {{
            background: rgba(59, 130, 246, 0.15);
            color: {ACCENT} !important;
        }}

        /* Dataframes / tables */
        [data-testid="stDataFrame"] {{
            border: 1px solid {SURFACE_BORDER};
            border-radius: 10px;
            overflow: hidden;
        }}

        /* Buttons */
        .stButton > button, .stFormSubmitButton > button {{
            border-radius: 8px;
            font-weight: 600;
        }}

        /* Badges (see status_badge()) */
        .fc-badge {{
            display: inline-flex;
            align-items: center;
            gap: 0.35rem;
            padding: 0.2rem 0.65rem;
            border-radius: 999px;
            font-size: 0.82rem;
            font-weight: 600;
        }}

        hr {{
            border-color: {SURFACE_BORDER} !important;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def status_badge(value: str, kind: str = "status") -> str:
    """
    Render an inline HTML pill for a status-like value (MATCHED/EXCEPTION,
    RESOLVED/UNRESOLVED/PENDING, AUTO_SUGGESTED/NEEDS_HUMAN_REVIEW/
    NOT_YET_INVESTIGATED). `kind` picks the icon set; color is derived from
    the semantic meaning (good/warn/bad) regardless of kind.
    """
    icon_map = {"status": STATUS_ICON, "ai_status": AI_STATUS_ICON, "decision": DECISION_ICON}.get(kind, {})
    icon = icon_map.get(value, "•")

    good_values = {"MATCHED", "RESOLVED", "AUTO_SUGGESTED"}
    bad_values = {"UNRESOLVED"}
    if value in good_values:
        color, bg = GOOD, GOOD_BG
    elif value in bad_values:
        color, bg = BAD, BAD_BG
    else:  # EXCEPTION, NEEDS_HUMAN_REVIEW, PENDING, NOT_YET_INVESTIGATED, etc.
        color, bg = WARN, WARN_BG

    label = value.replace("_", " ").title() if value else "—"
    return f'<span class="fc-badge" style="color:{color};background:{bg};">{icon} {label}</span>'


def status_cell_css(value) -> str:
    """
    CSS for a pandas Styler `.map()` call on a status-like dataframe column
    (MATCHED/EXCEPTION, RESOLVED/UNRESOLVED/PENDING, AUTO_SUGGESTED/
    NEEDS_HUMAN_REVIEW/NOT_YET_INVESTIGATED) -- colors the cell to match the
    semantic meaning, consistent with status_badge()'s palette.
    """
    good_values = {"MATCHED", "RESOLVED", "AUTO_SUGGESTED"}
    bad_values = {"UNRESOLVED"}
    if value in good_values:
        color, bg = GOOD, GOOD_BG
    elif value in bad_values:
        color, bg = BAD, BAD_BG
    elif pd_isna(value):
        return ""
    else:
        color, bg = WARN, WARN_BG
    return f"background-color: {bg}; color: {color}; font-weight: 600;"


def pd_isna(value) -> bool:
    """Local null-check avoiding a top-level pandas import in this module."""
    return value is None or (isinstance(value, float) and value != value)
