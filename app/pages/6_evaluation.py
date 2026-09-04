"""
FinControl AI - Evaluation page (Module 10, page 6)
========================================================
Renders evaluation/results.json (Module 9) directly -- every number here
is real, reproducible, and traces back to that file. Nothing hand-typed.
"""

import os
import sys

import streamlit as st

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.common import apply_theme, load_results  # noqa: E402
from evaluation.evaluate import run as run_evaluation  # noqa: E402

st.set_page_config(page_title="Evaluation – FinControl AI", page_icon="\U0001f4a0", layout="wide")
apply_theme()
st.title("Evaluation")
st.caption("Every number below is read from evaluation/results.json — nothing hand-typed.")

results = load_results()

with st.container(border=True):
    col_btn, col_note = st.columns([1, 2])
    with col_btn:
        if st.button("↻ Re-run evaluation (free & instant)"):
            with st.spinner("Re-running matcher + classifier against ground truth..."):
                results = run_evaluation()
            st.success("Done — evaluation/results.json updated.")
    with col_note:
        st.caption(
            "This re-runs the deterministic part only (Module 2+3+9). To refresh the AI-resolution "
            "numbers below, run `python -m evaluation.evaluate --with-ai` from a terminal (uses your Groq quota)."
        )

if results is None:
    st.warning("No results yet. Click the button above, or run `python -m evaluation.evaluate` from a terminal.")
    st.stop()

d, r, c, t = results["dataset"], results["reconciliation"], results["classification"], results["throughput"]
ai = results.get("ai_resolution")

st.divider()
st.subheader("📦 Dataset")
with st.container(border=True):
    cols = st.columns(3)
    cols[0].metric("Total records", d["total_records"])
    cols[1].metric("Expected matched", d["expected_matched"])
    cols[2].metric("Expected exceptions", d["expected_exceptions"])

st.subheader("🎯 Reconciliation (Module 2)")
with st.container(border=True):
    cols = st.columns(4)
    cols[0].metric("Match rate", f"{r['match_rate']:.1%}")
    cols[1].metric("Precision", f"{r['precision']:.1%}")
    cols[2].metric("Recall", f"{r['recall']:.1%}")
    cols[3].metric("F1", f"{r['f1']:.1%}")
    cols = st.columns(4)
    cols[0].metric("False positive rate", f"{r['false_positive_rate']:.1%}")
    cols[1].metric("True positives", r["true_positives_exceptions"])
    cols[2].metric("False positives", r["false_positives_exceptions"])
    cols[3].metric("False negatives", r["false_negatives_exceptions"])

st.subheader("🏷️ Exception classification (Module 3)")
with st.container(border=True):
    cols = st.columns(2)
    cols[0].metric("Exception-type accuracy", f"{c['exception_type_accuracy']:.1%}")
    cols[1].metric("Correct / total", f"{c['exception_type_correct']} / {c['exception_type_total']}")

st.subheader("🤖 AI resolution (Module 5 + 6)")
if ai:
    with st.container(border=True):
        cols = st.columns(5)
        cols[0].metric("Resolved", ai["resolved_count"])
        cols[1].metric("Resolution accuracy", f"{ai['resolution_accuracy']:.1%}")
        cols[2].metric("System UNRESOLVED", ai["system_unresolved_count"])
        cols[3].metric("True UNRESOLVED", ai["true_unresolved_count"])
        cols[4].metric(
            "False auto-resolves", ai["false_auto_resolve_count"],
            help="RESOLVED with high confidence but the cause was wrong -- the case this whole "
                 "system is built to prevent from reaching a human as a confident, unsupported claim.",
        )
else:
    st.info(
        "Not run yet. Add `GROQ_API_KEY` to `.env` (free at console.groq.com/keys), then run "
        "`python -m evaluation.evaluate --with-ai` from a terminal."
    )

st.subheader("⚡ Throughput")
with st.container(border=True):
    cols = st.columns(2)
    cols[0].metric("Records / second", f"{t['records_per_second']:,.0f}" if t["records_per_second"] else "—")
    cols[1].metric("Elapsed", f"{t['elapsed_seconds']:.3f}s" if t["elapsed_seconds"] else "—")

with st.expander("Raw evaluation/results.json"):
    st.json(results)
