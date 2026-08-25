"""
Unit tests for evaluation/evaluate.py (Module 9, v1: matcher+classifier only).

Run:
    pytest tests/test_evaluate.py -v
"""

import os
import sys
from unittest.mock import patch

import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from evaluation.evaluate import evaluate, run, run_with_ai


def test_perfect_match_gives_100_percent_everything():
    classified = pd.DataFrame([
        {"transaction_id": "t1", "status": "MATCHED", "exception_type": "NONE"},
        {"transaction_id": "t2", "status": "EXCEPTION", "exception_type": "FEE_DEDUCTION"},
    ])
    ground_truth = pd.DataFrame([
        {"transaction_id": "t1", "expected_status": "MATCHED", "expected_exception_type": "NONE"},
        {"transaction_id": "t2", "expected_status": "EXCEPTION", "expected_exception_type": "FEE_DEDUCTION"},
    ])
    results = evaluate(classified, ground_truth)
    assert results["reconciliation"]["match_rate"] == 1.0
    assert results["reconciliation"]["precision"] == 1.0
    assert results["reconciliation"]["recall"] == 1.0
    assert results["reconciliation"]["f1"] == 1.0
    assert results["classification"]["exception_type_accuracy"] == 1.0
    assert results["ai_resolution"] is None


def test_false_positive_and_false_negative_counted():
    classified = pd.DataFrame([
        {"transaction_id": "t1", "status": "EXCEPTION", "exception_type": "AMOUNT_MISMATCH"},  # FP
        {"transaction_id": "t2", "status": "MATCHED", "exception_type": "NONE"},  # FN
    ])
    ground_truth = pd.DataFrame([
        {"transaction_id": "t1", "expected_status": "MATCHED", "expected_exception_type": "NONE"},
        {"transaction_id": "t2", "expected_status": "EXCEPTION", "expected_exception_type": "FEE_DEDUCTION"},
    ])
    results = evaluate(classified, ground_truth)
    assert results["reconciliation"]["false_positives_exceptions"] == 1
    assert results["reconciliation"]["false_negatives_exceptions"] == 1
    assert results["reconciliation"]["match_rate"] == 0.0


def test_ai_resolution_metrics():
    classified = pd.DataFrame([
        {"transaction_id": "t1", "status": "EXCEPTION", "exception_type": "FEE_DEDUCTION"},
        {"transaction_id": "t2", "status": "EXCEPTION", "exception_type": "AMOUNT_MISMATCH"},  # AI got this wrong
        {"transaction_id": "t3", "status": "EXCEPTION", "exception_type": "UNCLASSIFIED_DIFFERENCE"},
    ])
    ground_truth = pd.DataFrame([
        {"transaction_id": "t1", "expected_status": "EXCEPTION", "expected_exception_type": "FEE_DEDUCTION",
         "expected_resolution": "AUTO_EXPLAIN"},
        {"transaction_id": "t2", "expected_status": "EXCEPTION", "expected_exception_type": "PARTIAL_REFUND",
         "expected_resolution": "AUTO_EXPLAIN"},
        {"transaction_id": "t3", "expected_status": "EXCEPTION", "expected_exception_type": "UNRESOLVED",
         "expected_resolution": "UNRESOLVED"},
        {"transaction_id": "t3_extra_matched", "expected_status": "MATCHED", "expected_exception_type": "NONE",
         "expected_resolution": "NO_ACTION"},
    ])
    # classified needs a row for every ground_truth transaction_id (inner join on transaction_id)
    classified = pd.concat([classified, pd.DataFrame([
        {"transaction_id": "t3_extra_matched", "status": "MATCHED", "exception_type": "NONE"}
    ])], ignore_index=True)

    ai_results = pd.DataFrame([
        {"transaction_id": "t1", "ai_status": "RESOLVED"},   # correct
        {"transaction_id": "t2", "ai_status": "RESOLVED"},   # wrong -- false auto-resolve
        {"transaction_id": "t3", "ai_status": "UNRESOLVED"},  # honest refusal
    ])

    results = evaluate(classified, ground_truth, ai_results=ai_results)
    a = results["ai_resolution"]
    assert a["resolved_count"] == 2
    assert a["resolution_accuracy"] == pytest.approx(0.5)  # 1 of 2 RESOLVED calls correct
    assert a["false_auto_resolve_count"] == 1
    assert a["system_unresolved_count"] == 1
    assert a["true_unresolved_count"] == 1


def test_run_with_ai_mocked_end_to_end():
    fake_investigated = [{
        "transaction_id": "pay_0001", "probable_cause": "fee", "evidence_used": ["fee_policy.md"],
        "confidence": 0.9, "recommendation": "ok", "status": "RESOLVED",
    }]
    fake_decided = [{**fake_investigated[0], "decision": "AUTO_SUGGESTED"}]

    with patch("agents.investigator.investigate_all", return_value=fake_investigated) as mock_investigate, \
         patch("agents.decision.decide_all", return_value=fake_decided):
        results, classified, decided = run_with_ai()

    mock_investigate.assert_called_once()
    assert results["ai_resolution"] is not None
    assert results["ai_resolution"]["resolved_count"] == 1
    assert decided == fake_decided


def test_end_to_end_run_against_real_synthetic_data():
    results = run()
    assert results["dataset"]["total_records"] == 91
    assert results["reconciliation"]["match_rate"] == 1.0
    assert results["reconciliation"]["f1"] == 1.0
    assert results["throughput"]["records_per_second"] > 0
    assert results["ai_resolution"] is None  # v1: no AI results supplied
