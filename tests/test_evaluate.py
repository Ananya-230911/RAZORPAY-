"""
Unit tests for evaluation/evaluate.py (Module 9, v1: matcher+classifier only).

Run:
    pytest tests/test_evaluate.py -v
"""

import os
import sys

import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from evaluation.evaluate import evaluate, run


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


def test_end_to_end_run_against_real_synthetic_data():
    results = run()
    assert results["dataset"]["total_records"] == 91
    assert results["reconciliation"]["match_rate"] == 1.0
    assert results["reconciliation"]["f1"] == 1.0
    assert results["throughput"]["records_per_second"] > 0
    assert results["ai_resolution"] is None  # v1: no AI results supplied
