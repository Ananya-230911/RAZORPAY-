"""
FinControl AI - Exception Investigation page (Module 8 + 10, page 3)
=========================================================================
Click one exception, see its full trail: mismatch -> retrieved evidence ->
AI reasoning -> confidence -> recommendation -> human decision. This is
also where Module 8's human-approval actions live: Approve / Reject /
Mark Unresolved, each clearly labeled SIMULATED and written to
fincontrol.db + audit_log.
"""

import os
import sys

import streamlit as st

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.common import get_full_case, record_human_decision, require_data, simulated_banner  # noqa: E402
from database.db import get_transactions  # noqa: E402
from rag.retriever import PolicyRetriever, build_query  # noqa: E402

st.set_page_config(page_title="Investigation – FinControl AI", page_icon="\U0001f50d", layout="wide")
st.title("Exception Investigation")
simulated_banner()

conn = require_data()
tx = get_transactions(conn)
exceptions = tx[tx["status"] == "EXCEPTION"].sort_values("transaction_id")

if exceptions.empty:
    st.info("No exceptions in this batch — everything reconciled cleanly.")
    st.stop()

tx_id = st.selectbox("Transaction", exceptions["transaction_id"].tolist())
case = get_full_case(conn, tx_id)
conn.close()

record = case["transaction"]
investigation = case["investigation"]
human_decisions = case["human_decisions"]

st.divider()

# --- 1. The mismatch (deterministic, Module 2+3) -----------------------------
st.subheader("1. The mismatch")
cols = st.columns(5)
cols[0].metric("Exception type", record["exception_type"] or "—")
cols[1].metric("Payment", f"{record['payment_amt']:.2f}" if record["payment_amt"] is not None else "—")
cols[2].metric("Invoice", f"{record['invoice_amt']:.2f}" if record["invoice_amt"] is not None else "—")
cols[3].metric("Settlement", f"{record['settlement_amt']:.2f}" if record["settlement_amt"] is not None else "—")
cols[4].metric("Difference", f"{record['difference']:.2f}" if record["difference"] is not None else "—")
st.caption(
    f"Records present: `{record['records_present']}` · "
    f"Date gap: {record['date_gap_days']} days · "
    f"Duplicate: {'yes' if record['is_duplicate'] else 'no'} · "
    f"Merchant: {record['merchant'] or '—'}"
)

# --- 2. Retrieved evidence (Module 4, re-run live for display) ---------------
st.subheader("2. Retrieved policy evidence")
retriever = PolicyRetriever()
query = build_query(record["exception_type"], dict(record))
evidence = retriever.retrieve(query)
if evidence:
    for e in evidence:
        with st.expander(f"📄 {e['source']} — {e['heading']}  (relevance {e['score']:.2f})"):
            st.write(e["snippet"])
else:
    st.caption("No policy evidence matched this exception.")

# --- 3. AI reasoning (Module 5+6) --------------------------------------------
st.subheader("3. AI investigation")
if investigation is None:
    st.info(
        "Not yet investigated. Add `GROQ_API_KEY` to `.env` and run "
        "`python -m evaluation.evaluate --with-ai` (or `python run.py`) to populate this."
    )
else:
    status_icon = "✅" if investigation["ai_status"] == "RESOLVED" else "❓"
    decision_icon = "🟢" if investigation["decision"] == "AUTO_SUGGESTED" else "🟡"
    st.markdown(f"**Status:** {status_icon} {investigation['ai_status']}  ·  "
                f"**Decision:** {decision_icon} {investigation['decision']}  ·  "
                f"**Confidence:** {investigation['confidence']:.0%}")
    st.markdown(f"**Probable cause:** {investigation['probable_cause'] or '_none — evidence was insufficient_'}")
    st.markdown(f"**Evidence cited:** {', '.join(investigation['evidence_used']) or '_none_'}")
    st.markdown(f"**Recommendation:** {investigation['recommendation']}")

# --- 4. Human decision (Module 8, SIMULATED) ---------------------------------
st.subheader("4. Human decision — SIMULATED, no real action taken")

if human_decisions:
    st.caption("Decision history for this transaction:")
    for hd in human_decisions:
        st.write(f"- `{hd['created_at']}` — **{hd['action']}** by {hd['actor']}"
                  + (f" — _{hd['note']}_" if hd["note"] else ""))

with st.form(key=f"decision_form_{tx_id}", clear_on_submit=True):
    action = st.radio("Action", ["APPROVE", "REJECT", "MARK_UNRESOLVED"], horizontal=True)
    note = st.text_area("Note (optional)", placeholder="Why are you making this call?")
    submitted = st.form_submit_button("Record decision (SIMULATED)")

if submitted:
    conn = require_data()
    record_human_decision(conn, tx_id, action, note=note, actor="human (dashboard)")
    conn.close()
    st.success(f"Recorded: {action} on {tx_id}. This is SIMULATED — no real money moved.")
    st.rerun()
