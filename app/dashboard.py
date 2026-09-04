"""
FinControl AI - Dashboard entry point (Module 8 + 10)
=========================================================
Landing page. The 6 real pages live in app/pages/ -- Streamlit auto-
discovers them for the sidebar. Every page reads from fincontrol.db
(Module 7) and evaluation/results.json (Module 9) only; nothing here is
hand-typed.

Run:
    streamlit run app/dashboard.py
    (or just: python run.py  -- runs the full pipeline first, then this)
"""

import os
import sys

import streamlit as st

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.common import apply_theme, get_conn, get_transactions, load_results  # noqa: E402

st.set_page_config(page_title="FinControl AI", page_icon="\U0001f4a0", layout="wide")
apply_theme()

st.title("\U0001f4a0 FinControl AI")
st.caption("AI Finance Controller — Razorpay AI Buildathon 2026, Track 4")

st.markdown(
    """
Deterministic Python does the reconciliation math. An AI investigator, grounded only in
retrieved policy evidence, looks at the exceptions that genuinely need judgment — and it
says **UNRESOLVED** instead of guessing whenever the evidence isn't there.
"""
)

conn = get_conn()
results = load_results()

if conn is None or results is None:
    st.info(
        "No pipeline run yet. From a terminal in the project root:\n\n"
        "```bash\npython run.py --seed 42\n```\n\n"
        "Then come back to this page."
    )
else:
    tx_df = get_transactions(conn)
    reconciliation = results["reconciliation"]
    ai = results.get("ai_resolution")
    conn.close()

    with st.container(border=True):
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Transactions", len(tx_df))
        c2.metric("Match rate", f"{reconciliation['match_rate']:.1%}")
        c3.metric("Exceptions", int((tx_df["status"] == "EXCEPTION").sum()))
        c4.metric("AI resolved", ai["resolved_count"] if ai else "—")
        c5.metric("Unresolved", ai["system_unresolved_count"] if ai else "—")

    if ai is None:
        st.caption(
            "AI investigation hasn't run yet (needs `GROQ_API_KEY` in `.env`). "
            "Reconciliation and classification results below are already real and final."
        )

st.divider()
st.markdown(
    """
**Pages** (see the sidebar): **Overview** · **Reconciliation Table** ·
**Exception Investigation** · **Exception Queue** · **Audit Log** · **Evaluation**

Start with **Overview** for the big picture, or jump straight to **Exception Investigation**
to see one case's full trail: mismatch → evidence → AI reasoning → confidence →
recommendation → human decision.
"""
)
