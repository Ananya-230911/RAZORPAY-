"""
Unit tests for run.py (Module 11: end-to-end pipeline orchestration).

Run:
    pytest tests/test_run.py -v
"""

import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from reconciliation.classifier import classify
from reconciliation.matcher import run as run_matcher

import run as run_module


def test_investigate_and_decide_skips_without_api_key():
    classified = classify(run_matcher())
    with patch.dict(os.environ, {}, clear=True):
        decided = run_module.investigate_and_decide(classified, skip_ai=False)
    assert decided is None  # graceful skip, not a crash


def test_investigate_and_decide_skips_when_flag_passed():
    classified = classify(run_matcher())
    with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "fake"}):
        decided = run_module.investigate_and_decide(classified, skip_ai=True)
    assert decided is None


def test_investigate_and_decide_calls_ai_when_key_present():
    classified = classify(run_matcher())
    fake_result = [{"transaction_id": "pay_0001", "status": "RESOLVED", "confidence": 0.9,
                     "probable_cause": "fee", "evidence_used": ["fee_policy.md"], "recommendation": "ok"}]
    with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "fake"}), \
         patch("run.investigate_all", return_value=fake_result) as mock_investigate:
        decided = run_module.investigate_and_decide(classified, skip_ai=False)
    mock_investigate.assert_called_once()
    assert decided[0]["decision"] == "AUTO_SUGGESTED"


def test_store_and_evaluate_full_pipeline_without_ai(tmp_path):
    db_path = str(tmp_path / "test.db")
    classified = classify(run_matcher())
    run_module.store(classified, decided=None, db_path=db_path)

    from database.db import get_connection, get_transactions
    conn = get_connection(db_path)
    stored = get_transactions(conn)
    assert len(stored) == len(classified)

    results = run_module.run_evaluation(classified, None, run_module.DEFAULT_DATA_DIR, elapsed_seconds=0.1)
    assert results["reconciliation"]["match_rate"] == 1.0
    assert results["ai_resolution"] is None
