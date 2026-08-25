"""
Unit tests for agents/decision.py (Module 6).

Run:
    pytest tests/test_decision.py -v
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agents.decision import decide, decide_all


def test_high_confidence_resolved_is_auto_suggested():
    r = decide({"transaction_id": "t1", "status": "RESOLVED", "confidence": 0.8})
    assert r["decision"] == "AUTO_SUGGESTED"


def test_just_below_threshold_needs_review():
    r = decide({"transaction_id": "t1", "status": "RESOLVED", "confidence": 0.79})
    assert r["decision"] == "NEEDS_HUMAN_REVIEW"


def test_unresolved_always_needs_review_even_with_high_confidence():
    """UNRESOLVED must always win, regardless of the confidence number --
    an inconsistent AI output (UNRESOLVED but high confidence) should never
    slip through as auto-suggested."""
    r = decide({"transaction_id": "t1", "status": "UNRESOLVED", "confidence": 0.95})
    assert r["decision"] == "NEEDS_HUMAN_REVIEW"


def test_missing_confidence_defaults_to_needs_review():
    r = decide({"transaction_id": "t1", "status": "RESOLVED"})
    assert r["decision"] == "NEEDS_HUMAN_REVIEW"


def test_decide_all_preserves_order_and_count():
    inputs = [
        {"transaction_id": "t1", "status": "RESOLVED", "confidence": 0.9},
        {"transaction_id": "t2", "status": "UNRESOLVED", "confidence": 0.1},
    ]
    out = decide_all(inputs)
    assert [r["transaction_id"] for r in out] == ["t1", "t2"]
    assert out[0]["decision"] == "AUTO_SUGGESTED"
    assert out[1]["decision"] == "NEEDS_HUMAN_REVIEW"


def test_decide_does_not_mutate_input():
    original = {"transaction_id": "t1", "status": "RESOLVED", "confidence": 0.9}
    decide(original)
    assert "decision" not in original
