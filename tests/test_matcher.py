"""
Unit tests for reconciliation/matcher.py (Module 2).

Run:
    pytest tests/test_matcher.py -v
"""

import os
import sys

import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from reconciliation.matcher import load_data, reconcile, run, DEFAULT_DATA_DIR


def test_full_pipeline_matches_ground_truth_counts():
    """End-to-end: matcher output on the real synthetic data must match the
    known MATCHED/EXCEPTION split from ground_truth.csv (35 / 56)."""
    df = run()
    gt = pd.read_csv(os.path.join(DEFAULT_DATA_DIR, "ground_truth.csv"))

    assert len(df) == len(gt)
    assert (df["status"] == "MATCHED").sum() == (gt["expected_status"] == "MATCHED").sum()
    assert (df["status"] == "EXCEPTION").sum() == (gt["expected_status"] == "EXCEPTION").sum()


def test_clean_match_is_matched():
    payments = pd.DataFrame([{"transaction_id": "t1", "amount": 100.0, "date": "2026-06-01",
                               "method": "card", "merchant": "M", "status": "captured"}])
    invoices = pd.DataFrame([{"transaction_id": "t1", "amount": 100.0, "date": "2026-06-01", "merchant": "M"}])
    settlements = pd.DataFrame([{"transaction_id": "t1", "amount": 100.0, "date": "2026-06-03",
                                  "fee_deducted": 0.0, "merchant": "M"}])
    df = reconcile(payments, invoices, settlements)
    row = df.iloc[0]
    assert row["status"] == "MATCHED"
    assert row["difference"] == 0.0
    assert row["records_present"] == "PAYMENT,INVOICE,SETTLEMENT"


def test_missing_invoice_is_exception():
    payments = pd.DataFrame([{"transaction_id": "t1", "amount": 100.0, "date": "2026-06-01",
                               "method": "card", "merchant": "M", "status": "captured"}])
    invoices = pd.DataFrame(columns=["transaction_id", "amount", "date", "merchant"])
    settlements = pd.DataFrame([{"transaction_id": "t1", "amount": 100.0, "date": "2026-06-03",
                                  "fee_deducted": 0.0, "merchant": "M"}])
    df = reconcile(payments, invoices, settlements)
    row = df.iloc[0]
    assert row["status"] == "EXCEPTION"
    assert row["records_present"] == "PAYMENT,SETTLEMENT"


def test_amount_mismatch_is_exception_with_correct_difference():
    payments = pd.DataFrame([{"transaction_id": "t1", "amount": 100.0, "date": "2026-06-01",
                               "method": "card", "merchant": "M", "status": "captured"}])
    invoices = pd.DataFrame([{"transaction_id": "t1", "amount": 100.0, "date": "2026-06-01", "merchant": "M"}])
    settlements = pd.DataFrame([{"transaction_id": "t1", "amount": 90.0, "date": "2026-06-03",
                                  "fee_deducted": 0.0, "merchant": "M"}])
    df = reconcile(payments, invoices, settlements)
    row = df.iloc[0]
    assert row["status"] == "EXCEPTION"
    assert row["difference"] == pytest.approx(10.0)


def test_duplicate_transactions_flagged_and_excepted():
    payments = pd.DataFrame([
        {"transaction_id": "t1", "amount": 100.0, "date": "2026-06-01",
         "method": "card", "merchant": "M", "status": "captured"},
        {"transaction_id": "t2", "amount": 100.0, "date": "2026-06-01",
         "method": "card", "merchant": "M", "status": "captured"},
    ])
    invoices = pd.DataFrame([{"transaction_id": "t1", "amount": 100.0, "date": "2026-06-01", "merchant": "M"}])
    settlements = pd.DataFrame([{"transaction_id": "t1", "amount": 100.0, "date": "2026-06-03",
                                  "fee_deducted": 0.0, "merchant": "M"}])
    df = reconcile(payments, invoices, settlements)
    assert df.set_index("transaction_id").loc["t1", "is_duplicate"]
    assert df.set_index("transaction_id").loc["t2", "is_duplicate"]
    # t1 would otherwise look clean (payment==invoice==settlement) but must
    # still be flagged EXCEPTION because it's part of a duplicate pair.
    assert df.set_index("transaction_id").loc["t1", "status"] == "EXCEPTION"


def test_missing_file_raises_clear_error(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_data(str(tmp_path))


def test_empty_csv_raises_clear_error(tmp_path):
    (tmp_path / "payments.csv").write_text("payment_id,transaction_id,amount,date,method,merchant,status\n")
    (tmp_path / "invoices.csv").write_text("invoice_id,transaction_id,amount,date,merchant\n")
    (tmp_path / "settlements.csv").write_text("settlement_id,transaction_id,amount,date,fee_deducted,merchant\n")
    with pytest.raises(ValueError):
        load_data(str(tmp_path))
