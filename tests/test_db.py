"""
Unit tests for database/db.py (Module 7).

Run:
    pytest tests/test_db.py -v
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from reconciliation.classifier import classify
from reconciliation.matcher import run as run_matcher

from database.db import (
    get_audit_log,
    get_full_case,
    get_human_decisions,
    get_investigations,
    get_transactions,
    init_db,
    record_human_decision,
    write_investigations,
    write_transactions,
)


def _fresh_db(tmp_path):
    return init_db(str(tmp_path / "test.db"))


def test_write_transactions_round_trips_real_data(tmp_path):
    conn = _fresh_db(tmp_path)
    classified = classify(run_matcher())
    write_transactions(conn, classified)

    stored = get_transactions(conn)
    assert len(stored) == len(classified)
    assert set(stored["status"]) <= {"MATCHED", "EXCEPTION"}

    audit = get_audit_log(conn)
    assert len(audit) == 1
    assert audit.iloc[0]["actor"] == "system"
    assert audit.iloc[0]["action"] == "RECONCILE_AND_CLASSIFY"


def test_write_transactions_upserts_on_rerun(tmp_path):
    conn = _fresh_db(tmp_path)
    classified = classify(run_matcher())
    write_transactions(conn, classified)
    write_transactions(conn, classified)  # simulate re-running the pipeline

    stored = get_transactions(conn)
    assert len(stored) == len(classified)  # no duplicates
    assert len(get_audit_log(conn)) == 2  # but both runs are audited


def test_write_investigations_stores_evidence_and_audits(tmp_path):
    conn = _fresh_db(tmp_path)
    write_transactions(conn, classify(run_matcher()))  # investigations FK-reference transactions
    results = [{
        "transaction_id": "pay_0001", "probable_cause": "platform fee deducted",
        "evidence_used": ["fee_policy.md"], "confidence": 0.91,
        "recommendation": "auto-explain", "status": "RESOLVED", "decision": "AUTO_SUGGESTED",
    }]
    write_investigations(conn, results)

    stored = get_investigations(conn)
    assert len(stored) == 1
    assert stored.iloc[0]["evidence_used"] == ["fee_policy.md"]
    assert stored.iloc[0]["decision"] == "AUTO_SUGGESTED"

    audit = get_audit_log(conn)
    assert audit.iloc[0]["actor"] == "AI"
    assert audit.iloc[0]["evidence_ref"] == "fee_policy.md"


def test_record_human_decision_and_full_case(tmp_path):
    conn = _fresh_db(tmp_path)
    classified = classify(run_matcher())
    write_transactions(conn, classified)
    write_investigations(conn, [{
        "transaction_id": "pay_0001", "probable_cause": "fee", "evidence_used": ["fee_policy.md"],
        "confidence": 0.91, "recommendation": "auto-explain", "status": "RESOLVED", "decision": "AUTO_SUGGESTED",
    }])

    record_human_decision(conn, "pay_0001", "APPROVE", note="Looks right, approving.", actor="human")

    decisions = get_human_decisions(conn)
    assert len(decisions) == 1
    assert decisions.iloc[0]["action"] == "APPROVE"

    case = get_full_case(conn, "pay_0001")
    assert case["transaction"]["transaction_id"] == "pay_0001"
    assert case["investigation"]["probable_cause"] == "fee"
    assert len(case["human_decisions"]) == 1

    audit = get_audit_log(conn)
    assert "HUMAN_APPROVE" in audit["action"].values


def test_get_full_case_for_unknown_transaction_returns_none_fields(tmp_path):
    conn = _fresh_db(tmp_path)
    case = get_full_case(conn, "does_not_exist")
    assert case["transaction"] is None
    assert case["investigation"] is None
    assert case["human_decisions"] == []
