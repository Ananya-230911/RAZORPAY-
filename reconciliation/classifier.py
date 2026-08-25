"""
FinControl AI - Exception Classifier
=====================================
Module 3 of the pipeline. Rule-based (if/else) tagging ONLY -- no AI. Takes
the EXCEPTION rows produced by reconciliation/matcher.py and assigns each
one an exception_type, using thresholds informed by the rag/policies docs
(fee %, refund %, T+2 settlement window).

This classifier is intentionally a first-pass heuristic, not a perfect
oracle: a handful of categories (small fee-like diffs vs. genuinely
ambiguous tiny diffs) overlap by design in the synthetic dataset, and are
exactly the cases the Investigation Agent (Module 5) exists to resolve with
grounded evidence -- or honestly mark UNRESOLVED. See evaluation/evaluate.py
for the real precision/recall numbers, not a hand-waved claim of 100%.

Input:  matcher.py output (a DataFrame with one row per transaction)
Output: same DataFrame, with an `exception_type` column added for every
        EXCEPTION row (MATCHED rows get "NONE").

Run directly for a quick sanity check:
    python reconciliation/classifier.py
"""

import pandas as pd

from reconciliation.matcher import AMOUNT_TOLERANCE, DATE_TOLERANCE_DAYS

# Fee policy: Razorpay-style platform fee is roughly 1.5%-2.5% of the
# payment amount (see rag/policies/fee_policy.md). Give it a little slack
# on both sides so genuine fee deductions aren't missed.
FEE_RATIO_MIN = 0.005   # 0.5%
FEE_RATIO_MAX = 0.10    # 10%

# Refund policy: a partial refund is a substantial fraction of the payment.
PARTIAL_REFUND_RATIO_MIN = 0.10  # 10%

# A "tiny" absolute rupee gap with no clean percentage explanation.
AMBIGUOUS_ABS_MAX = 15.0

EXCEPTION_TYPES = [
    "DUPLICATE_TRANSACTION", "UNKNOWN_TRANSACTION", "MISSING_INVOICE",
    "MISSING_SETTLEMENT", "DATE_MISMATCH", "FULL_REFUND", "PARTIAL_REFUND",
    "AMOUNT_MISMATCH", "FEE_DEDUCTION", "AMBIGUOUS_MINOR_DIFFERENCE",
    "UNCLASSIFIED_DIFFERENCE",
]


def _classify_row(row: pd.Series) -> str:
    if row["status"] != "EXCEPTION":
        return "NONE"

    if bool(row["is_duplicate"]):
        return "DUPLICATE_TRANSACTION"

    present = str(row["records_present"]).split(",")
    has_pay = "PAYMENT" in present
    has_inv = "INVOICE" in present
    has_stl = "SETTLEMENT" in present

    if not has_pay:
        return "UNKNOWN_TRANSACTION"
    if not has_inv:
        return "MISSING_INVOICE"
    if not has_stl:
        return "MISSING_SETTLEMENT"

    # All three records present but flagged EXCEPTION -> amount or date issue.
    payment_amt = row["payment_amt"]
    invoice_amt = row["invoice_amt"]
    settlement_amt = row["settlement_amt"]
    date_gap = row["date_gap_days"]

    amounts_all_equal = (
        abs(payment_amt - invoice_amt) <= AMOUNT_TOLERANCE
        and abs(payment_amt - settlement_amt) <= AMOUNT_TOLERANCE
    )
    if amounts_all_equal and date_gap is not None and abs(date_gap - 2) > DATE_TOLERANCE_DAYS:
        return "DATE_MISMATCH"

    if settlement_amt <= 0.01:
        return "FULL_REFUND"

    settle_diff = payment_amt - settlement_amt
    settle_ratio = settle_diff / payment_amt if payment_amt else 0
    inv_diff = invoice_amt - payment_amt

    if settle_ratio >= PARTIAL_REFUND_RATIO_MIN:
        return "PARTIAL_REFUND"

    if abs(inv_diff) > AMOUNT_TOLERANCE and abs(settlement_amt - payment_amt) <= AMOUNT_TOLERANCE:
        return "AMOUNT_MISMATCH"

    if FEE_RATIO_MIN <= settle_ratio < FEE_RATIO_MAX and abs(inv_diff) <= AMOUNT_TOLERANCE:
        return "FEE_DEDUCTION"

    if abs(settle_diff) <= AMBIGUOUS_ABS_MAX:
        return "AMBIGUOUS_MINOR_DIFFERENCE"

    return "UNCLASSIFIED_DIFFERENCE"


def classify(reconciled: pd.DataFrame) -> pd.DataFrame:
    """Add an `exception_type` column to matcher.py's output DataFrame."""
    df = reconciled.copy()
    df["exception_type"] = df.apply(_classify_row, axis=1)
    return df


if __name__ == "__main__":
    from reconciliation.matcher import run as run_matcher

    reconciled = run_matcher()
    classified = classify(reconciled)
    counts = classified.loc[classified["status"] == "EXCEPTION", "exception_type"].value_counts()
    print(f"Classified {len(classified)} transactions ({(classified['status'] == 'EXCEPTION').sum()} exceptions)")
    print()
    print(counts.to_string())
