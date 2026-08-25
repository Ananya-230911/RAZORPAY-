"""
Unit tests for agents/investigator.py (Module 5).

These tests never call the real Groq API -- the client is mocked so the
tests are fast, free, and deterministic. What they actually verify is the
part that matters most: the code-side enforcement of the "never guess"
rule (_enforce_evidence_rule) and malformed-JSON handling, independent of
whatever the model actually says.

Run:
    pytest tests/test_investigator.py -v
"""

import json
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agents.investigator import (
    InvestigationResult,
    MissingAPIKeyError,
    _enforce_evidence_rule,
    _parse_llm_json,
    investigate_all,
    investigate_exception,
)

FAKE_EVIDENCE = [{"source": "fee_policy.md", "heading": "Standard transaction fee", "snippet": "...", "score": 0.5}]


def _row(**overrides):
    row = {
        "transaction_id": "pay_0001", "exception_type": "FEE_DEDUCTION",
        "records_present": "PAYMENT,INVOICE,SETTLEMENT",
        "payment_amt": 1000.0, "invoice_amt": 1000.0, "settlement_amt": 980.0,
        "difference": 20.0, "date_gap_days": 2, "is_duplicate": False,
    }
    row.update(overrides)
    return row


def _mock_client(content: str):
    """Build a mock Groq client whose chat.completions.create() returns
    `content` as the assistant message text (mirrors the OpenAI-compatible
    response shape Groq uses)."""
    client = MagicMock()
    response = MagicMock()
    response.choices = [MagicMock(message=MagicMock(content=content))]
    client.chat.completions.create.return_value = response
    return client


def _valid_json(**overrides):
    payload = {
        "transaction_id": "pay_0001", "probable_cause": "platform fee deducted",
        "evidence_used": ["fee_policy.md"], "confidence": 0.9,
        "recommendation": "auto-explain, no action needed", "status": "RESOLVED",
    }
    payload.update(overrides)
    return json.dumps(payload)


# --- _enforce_evidence_rule: the core safety net -----------------------------

def test_confident_claim_with_evidence_passes_through():
    result = InvestigationResult(
        transaction_id="t1", probable_cause="fee deducted", evidence_used=["fee_policy.md"],
        confidence=0.9, recommendation="auto-explain", status="RESOLVED",
    )
    out = _enforce_evidence_rule(result, FAKE_EVIDENCE)
    assert out.status == "RESOLVED"
    assert out.confidence == 0.9


def test_confident_claim_with_no_evidence_is_downgraded():
    """The exact hard rule from the master build prompt: confidence > 0.5
    with no cited evidence must never survive, regardless of what the LLM said."""
    result = InvestigationResult(
        transaction_id="t1", probable_cause="fee deducted", evidence_used=[],
        confidence=0.91, recommendation="auto-explain", status="RESOLVED",
    )
    out = _enforce_evidence_rule(result, FAKE_EVIDENCE)
    assert out.status == "UNRESOLVED"
    assert out.probable_cause is None
    assert out.confidence == 0.0
    assert "failed validation" in out.recommendation


def test_hallucinated_citation_is_downgraded():
    """Citing a source that was never retrieved is treated as a violation
    even if confidence is low -- it's evidence the model is confabulating."""
    result = InvestigationResult(
        transaction_id="t1", probable_cause="fee deducted", evidence_used=["made_up_policy.md"],
        confidence=0.3, recommendation="auto-explain", status="RESOLVED",
    )
    out = _enforce_evidence_rule(result, FAKE_EVIDENCE)
    assert out.status == "UNRESOLVED"


def test_low_confidence_with_no_evidence_is_untouched():
    """A model honestly saying UNRESOLVED with low confidence and no
    evidence should NOT be flagged as a violation -- it already did the
    right thing."""
    result = InvestigationResult(
        transaction_id="t1", probable_cause=None, evidence_used=[],
        confidence=0.2, recommendation="route to human", status="UNRESOLVED",
    )
    out = _enforce_evidence_rule(result, FAKE_EVIDENCE)
    assert out.status == "UNRESOLVED"
    assert out.confidence == 0.2  # left as-is, not zeroed


# --- _parse_llm_json: defensive parsing ---------------------------------------

def test_parse_llm_json_plain():
    assert _parse_llm_json('{"a": 1}') == {"a": 1}


def test_parse_llm_json_strips_markdown_fences():
    assert _parse_llm_json('```json\n{"a": 1}\n```') == {"a": 1}


def test_parse_llm_json_strips_bare_fences():
    assert _parse_llm_json('```\n{"a": 1}\n```') == {"a": 1}


# --- investigate_exception: mocked end-to-end ---------------------------------

def test_investigate_exception_happy_path():
    client = _mock_client(_valid_json())
    out = investigate_exception(_row(), client=client)
    assert out["status"] == "RESOLVED"
    assert out["transaction_id"] == "pay_0001"
    client.chat.completions.create.assert_called_once()


def test_investigate_exception_recovers_from_malformed_json_on_retry():
    """First response is garbage (e.g. the model ignored JSON-mode
    instructions), second is valid -- the retry should save the call
    instead of the row being lost."""
    client = _mock_client("not json at all")
    response_ok = MagicMock()
    response_ok.choices = [MagicMock(message=MagicMock(content=_valid_json()))]
    client.chat.completions.create.side_effect = [client.chat.completions.create.return_value, response_ok]

    out = investigate_exception(_row(), client=client)
    assert out["status"] == "RESOLVED"
    assert client.chat.completions.create.call_count == 2


def test_investigate_exception_gives_up_honestly_after_retries_exhausted():
    """If every attempt returns unparseable JSON, fail as UNRESOLVED --
    never silently crash the batch or fabricate a result."""
    client = _mock_client("still not json")
    out = investigate_exception(_row(), client=client)
    assert out["status"] == "UNRESOLVED"
    assert out["confidence"] == 0.0
    assert client.chat.completions.create.call_count == 2  # 1 + MAX_RETRIES


def test_investigate_exception_rejects_non_exception_row():
    with pytest.raises(ValueError):
        investigate_exception(_row(exception_type="NONE"))


def test_investigate_exception_missing_api_key():
    with patch.dict(os.environ, {}, clear=True):
        with pytest.raises(MissingAPIKeyError):
            investigate_exception(_row())


# --- investigate_all: batch behavior -------------------------------------------

def test_investigate_all_fails_fast_without_api_key():
    with patch.dict(os.environ, {}, clear=True):
        with pytest.raises(MissingAPIKeyError):
            investigate_all([_row()])


def test_investigate_all_skips_matched_rows():
    with patch.dict(os.environ, {"GROQ_API_KEY": "fake-key-for-test"}):
        with patch("agents.investigator.groq.Groq") as MockGroq:
            instance = MockGroq.return_value
            response = MagicMock()
            response.choices = [MagicMock(message=MagicMock(content=_valid_json()))]
            instance.chat.completions.create.return_value = response

            rows = [_row(), {"transaction_id": "pay_0002", "exception_type": "NONE"}]
            results = investigate_all(rows, verbose=False)
            assert len(results) == 1
            assert results[0]["transaction_id"] == "pay_0001"
