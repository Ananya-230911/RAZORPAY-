"""
Unit tests for reconciliation/classifier.py (Module 3).

Run:
    pytest tests/test_classifier.py -v
"""

import os
import sys

import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from reconciliation.classifier import classify


def _base_row(**overrides):
    row = {
        "transaction_id": "t1", "status": "EXCEPTION",
        "payment_amt": 1000.0, "invoice_amt": 1000.0, "settlement_amt": 1000.0,
        "difference": 0.0, "records_present": "PAYMENT,INVOICE,SETTLEMENT",
        "date_gap_days": 2.0, "is_duplicate": False, "merchant": "M",
    }
    row.update(overrides)
    return row


def test_matched_rows_get_none():
    df = pd.DataFrame([_base_row(status="MATCHED")])
    out = classify(df)
    assert out.iloc[0]["exception_type"] == "NONE"


def test_duplicate_takes_priority():
    df = pd.DataFrame([_base_row(is_duplicate=True, payment_amt=500, invoice_amt=None, settlement_amt=None,
                                  records_present="PAYMENT")])
    out = classify(df)
    assert out.iloc[0]["exception_type"] == "DUPLICATE_TRANSACTION"


def test_missing_invoice():
    df = pd.DataFrame([_base_row(records_present="PAYMENT,SETTLEMENT", invoice_amt=None)])
    assert classify(df).iloc[0]["exception_type"] == "MISSING_INVOICE"


def test_missing_settlement():
    df = pd.DataFrame([_base_row(records_present="PAYMENT,INVOICE", settlement_amt=None, date_gap_days=None)])
    assert classify(df).iloc[0]["exception_type"] == "MISSING_SETTLEMENT"


def test_unknown_transaction_no_payment():
    df = pd.DataFrame([_base_row(records_present="SETTLEMENT", payment_amt=None, invoice_amt=None)])
    assert classify(df).iloc[0]["exception_type"] == "UNKNOWN_TRANSACTION"


def test_full_refund():
    df = pd.DataFrame([_base_row(settlement_amt=0.0)])
    assert classify(df).iloc[0]["exception_type"] == "FULL_REFUND"


def test_partial_refund():
    df = pd.DataFrame([_base_row(settlement_amt=600.0)])  # 40% off
    assert classify(df).iloc[0]["exception_type"] == "PARTIAL_REFUND"


def test_fee_deduction():
    df = pd.DataFrame([_base_row(settlement_amt=980.0)])  # 2% off, invoice matches payment
    assert classify(df).iloc[0]["exception_type"] == "FEE_DEDUCTION"


def test_amount_mismatch():
    df = pd.DataFrame([_base_row(invoice_amt=1200.0, settlement_amt=1000.0)])  # settlement matches payment, invoice doesn't
    assert classify(df).iloc[0]["exception_type"] == "AMOUNT_MISMATCH"


def test_date_mismatch():
    df = pd.DataFrame([_base_row(date_gap_days=30.0)])  # amounts all agree, date way off
    assert classify(df).iloc[0]["exception_type"] == "DATE_MISMATCH"


def test_ambiguous_minor_difference():
    df = pd.DataFrame([_base_row(settlement_amt=998.0)])  # 2 rupee gap, ratio 0.2% (below fee floor)
    assert classify(df).iloc[0]["exception_type"] == "AMBIGUOUS_MINOR_DIFFERENCE"


def test_full_reconciliation_pipeline_recovers_known_category_counts():
    """End-to-end sanity check against the real synthetic dataset."""
    from reconciliation.matcher import run as run_matcher

    reconciled = run_matcher()
    classified = classify(reconciled)
    exceptions = classified[classified["status"] == "EXCEPTION"]

    counts = exceptions["exception_type"].value_counts().to_dict()
    # These categories have zero ambiguity in the generator and must match exactly.
    assert counts["FEE_DEDUCTION"] == 8
    assert counts["DUPLICATE_TRANSACTION"] == 8
    assert counts["FULL_REFUND"] == 5
    assert counts["MISSING_INVOICE"] == 5
    assert counts["MISSING_SETTLEMENT"] == 5
    assert counts["DATE_MISMATCH"] == 4
    assert counts["UNKNOWN_TRANSACTION"] == 3
    assert counts["AMOUNT_MISMATCH"] == 6
    assert sum(counts.values()) == 56
