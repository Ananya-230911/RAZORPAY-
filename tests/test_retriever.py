"""
Unit tests for rag/retriever.py (Module 4).

Run:
    pytest tests/test_retriever.py -v
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from rag.retriever import PolicyRetriever, build_query


def test_loads_all_policy_files():
    r = PolicyRetriever()
    sources = {s["source"] for s in r.sections}
    assert sources == {"dispute_policy.md", "fee_policy.md", "refund_policy.md", "settlement_policy.md"}


def test_fee_deduction_query_retrieves_fee_policy():
    r = PolicyRetriever()
    query = build_query("FEE_DEDUCTION", {"payment_amt": 1000.0, "settlement_amt": 980.0, "invoice_amt": 1000.0})
    results = r.retrieve(query)
    assert results, "expected at least one matching section"
    assert results[0]["source"] == "fee_policy.md"


def test_partial_refund_query_retrieves_refund_policy():
    r = PolicyRetriever()
    query = build_query("PARTIAL_REFUND", {"payment_amt": 1000.0, "settlement_amt": 600.0, "invoice_amt": 1000.0})
    results = r.retrieve(query)
    assert results[0]["source"] == "refund_policy.md"


def test_missing_invoice_query_retrieves_dispute_policy():
    r = PolicyRetriever()
    query = build_query("MISSING_INVOICE", {"records_present": "PAYMENT,SETTLEMENT"})
    results = r.retrieve(query)
    assert results[0]["source"] == "dispute_policy.md"


def test_nonsense_query_returns_no_evidence():
    r = PolicyRetriever()
    results = r.retrieve("purple elephants dancing on the moon xyzzy", min_score=0.05)
    assert results == []


def test_retrieve_respects_top_k():
    r = PolicyRetriever()
    query = build_query("FEE_DEDUCTION", {"payment_amt": 1000.0, "settlement_amt": 980.0, "invoice_amt": 1000.0})
    results = r.retrieve(query, top_k=1)
    assert len(results) <= 1
