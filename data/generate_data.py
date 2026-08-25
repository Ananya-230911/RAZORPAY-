"""
FinControl AI - Synthetic Dataset Generator
=============================================
Generates a realistic synthetic batch of financial records across three
sources (payments, invoices, settlements) that must be reconciled.

Every record is generated with a KNOWN ground-truth label, so that later
(evaluation/evaluate.py) we can measure real precision/recall instead of
guessing whether the system got it right.

Run:
    python data/generate_data.py

Output (in data/synthetic/):
    payments.csv
    invoices.csv
    settlements.csv
    ground_truth.csv

Reproducible: uses a fixed random seed (42) unless overridden with --seed.
"""

import argparse
import csv
import os
import random
from datetime import datetime, timedelta

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

MERCHANTS = [
    "Blue Leaf Cafe", "Northwind Traders", "Pixel Studio", "Zenith Fitness",
    "Harbor Books", "Cloudline SaaS", "Terra Foods", "Nova Electronics",
    "Wren & Co", "Marigold Textiles",
]

METHODS = ["card", "upi", "netbanking", "wallet"]

# Category -> count. Sums to > 50 records as required (Razorpay: 50+ min).
CATEGORY_COUNTS = {
    "CLEAN_MATCH": 35,             # payment == invoice == settlement (minus nothing)
    "FEE_DEDUCTION": 8,            # settlement = payment - platform fee (explainable)
    "PARTIAL_REFUND": 6,           # settlement = payment - partial refund
    "FULL_REFUND": 5,              # settlement much lower / refunded fully
    "AMOUNT_MISMATCH": 6,          # invoice != payment, no clean explanation
    "MISSING_INVOICE": 5,          # payment + settlement exist, invoice never issued
    "MISSING_SETTLEMENT": 5,       # payment + invoice exist, not yet settled
    "DUPLICATE_TRANSACTION": 4,    # same amount/customer billed twice
    "DATE_MISMATCH": 4,            # settlement lands way outside normal T+2 window
    "UNKNOWN_TRANSACTION": 3,      # settlement with no matching payment at all
    "AMBIGUOUS_EXCEPTION": 3,      # tiny unexplained difference, weak evidence
    "UNRESOLVED": 3,               # genuinely no clean cause - should stay UNRESOLVED
}

BASE_DATE = datetime(2026, 6, 1)


def rand_amount(rng):
    return round(rng.uniform(200, 25000), 2)


def fmt(dt):
    return dt.strftime("%Y-%m-%d")


def make_records(seed=42):
    rng = random.Random(seed)

    payments, invoices, settlements, ground_truth = [], [], [], []
    tx_counter = 1

    def next_tx_id():
        nonlocal tx_counter
        tid = f"pay_{tx_counter:04d}"
        tx_counter += 1
        return tid

    for category, count in CATEGORY_COUNTS.items():
        for _ in range(count):
            tx_id = next_tx_id()
            merchant = rng.choice(MERCHANTS)
            method = rng.choice(METHODS)
            pay_date = BASE_DATE + timedelta(days=rng.randint(0, 60))
            amount = rand_amount(rng)

            # Defaults - overridden per category below
            payment_row = {
                "payment_id": f"rzp_{tx_id}", "transaction_id": tx_id,
                "amount": amount, "date": fmt(pay_date),
                "method": method, "merchant": merchant, "status": "captured",
            }
            invoice_row = {
                "invoice_id": f"inv_{tx_id}", "transaction_id": tx_id,
                "amount": amount, "date": fmt(pay_date), "merchant": merchant,
            }
            settlement_row = {
                "settlement_id": f"stl_{tx_id}", "transaction_id": tx_id,
                "amount": amount, "date": fmt(pay_date + timedelta(days=2)),
                "fee_deducted": 0.0, "merchant": merchant,
            }
            gt = {
                "transaction_id": tx_id,
                "category": category,
                "expected_status": "MATCHED",
                "expected_exception_type": "NONE",
                "expected_resolution": "NO_ACTION",
                "ground_truth_reason": "All three records agree.",
            }

            if category == "CLEAN_MATCH":
                pass  # defaults already correct

            elif category == "FEE_DEDUCTION":
                fee = round(amount * rng.uniform(0.015, 0.025), 2)  # ~1.5-2.5% fee
                settlement_row["amount"] = round(amount - fee, 2)
                settlement_row["fee_deducted"] = fee
                gt.update(expected_status="EXCEPTION",
                          expected_exception_type="FEE_DEDUCTION",
                          expected_resolution="AUTO_EXPLAIN",
                          ground_truth_reason=f"Platform fee of {fee} deducted at settlement; matches fee policy.")

            elif category == "PARTIAL_REFUND":
                refund = round(amount * rng.uniform(0.2, 0.5), 2)
                settlement_row["amount"] = round(amount - refund, 2)
                gt.update(expected_status="EXCEPTION",
                          expected_exception_type="PARTIAL_REFUND",
                          expected_resolution="AUTO_EXPLAIN",
                          ground_truth_reason=f"Partial refund of {refund} issued; settlement reflects net amount.")

            elif category == "FULL_REFUND":
                settlement_row["amount"] = 0.0
                gt.update(expected_status="EXCEPTION",
                          expected_exception_type="FULL_REFUND",
                          expected_resolution="AUTO_EXPLAIN",
                          ground_truth_reason="Transaction fully refunded; settlement amount is zero.")

            elif category == "AMOUNT_MISMATCH":
                # Invoice was raised for a different (wrong) amount than payment
                invoice_row["amount"] = round(amount + rng.choice([-1, 1]) * rng.uniform(50, 500), 2)
                gt.update(expected_status="EXCEPTION",
                          expected_exception_type="AMOUNT_MISMATCH",
                          expected_resolution="HUMAN_REVIEW",
                          ground_truth_reason="Invoice amount does not match payment amount; likely invoicing error.")

            elif category == "MISSING_INVOICE":
                invoice_row = None
                gt.update(expected_status="EXCEPTION",
                          expected_exception_type="MISSING_INVOICE",
                          expected_resolution="HUMAN_REVIEW",
                          ground_truth_reason="No invoice was ever generated for this payment.")

            elif category == "MISSING_SETTLEMENT":
                settlement_row = None
                gt.update(expected_status="EXCEPTION",
                          expected_exception_type="MISSING_SETTLEMENT",
                          expected_resolution="AUTO_EXPLAIN",
                          ground_truth_reason="Payment captured recently; settlement is still pending (within normal T+2 window or delayed).")

            elif category == "DUPLICATE_TRANSACTION":
                # Emit a second payment row with the same amount/customer, new tx id, no separate invoice/settlement issue
                dup_tx_id = next_tx_id()
                dup_payment = dict(payment_row)
                dup_payment["payment_id"] = f"rzp_{dup_tx_id}"
                dup_payment["transaction_id"] = dup_tx_id
                payments.append(dup_payment)
                ground_truth.append({
                    "transaction_id": dup_tx_id, "category": category,
                    "expected_status": "EXCEPTION", "expected_exception_type": "DUPLICATE_TRANSACTION",
                    "expected_resolution": "HUMAN_REVIEW",
                    "ground_truth_reason": f"Duplicate of {tx_id}: same amount/merchant/method charged twice.",
                })
                gt.update(expected_status="EXCEPTION",
                          expected_exception_type="DUPLICATE_TRANSACTION",
                          expected_resolution="HUMAN_REVIEW",
                          ground_truth_reason=f"Original transaction; {dup_tx_id} appears to be a duplicate charge.")

            elif category == "DATE_MISMATCH":
                settlement_row["date"] = fmt(pay_date + timedelta(days=rng.randint(20, 40)))
                gt.update(expected_status="EXCEPTION",
                          expected_exception_type="DATE_MISMATCH",
                          expected_resolution="HUMAN_REVIEW",
                          ground_truth_reason="Settlement date falls far outside the normal T+2 settlement window.")

            elif category == "UNKNOWN_TRANSACTION":
                payment_row = None
                invoice_row = None
                gt.update(expected_status="EXCEPTION",
                          expected_exception_type="UNKNOWN_TRANSACTION",
                          expected_resolution="HUMAN_REVIEW",
                          ground_truth_reason="Settlement record has no matching payment or invoice in our system.")

            elif category == "AMBIGUOUS_EXCEPTION":
                tiny_diff = round(rng.uniform(1, 15), 2)
                settlement_row["amount"] = round(amount - tiny_diff, 2)
                gt.update(expected_status="EXCEPTION",
                          expected_exception_type="AMBIGUOUS_MINOR_DIFFERENCE",
                          expected_resolution="HUMAN_REVIEW",
                          ground_truth_reason=f"Small unexplained difference of {tiny_diff}; no policy or evidence clearly accounts for it.")

            elif category == "UNRESOLVED":
                weird_diff = round(rng.uniform(100, 900), 2)
                settlement_row["amount"] = round(amount - weird_diff, 2)
                invoice_row["amount"] = round(amount + rng.uniform(-50, 50), 2)
                gt.update(expected_status="EXCEPTION",
                          expected_exception_type="UNRESOLVED",
                          expected_resolution="UNRESOLVED",
                          ground_truth_reason="No combination of fee/refund/date evidence explains this gap; genuinely inconclusive.")

            if payment_row is not None:
                payments.append(payment_row)
            if invoice_row is not None:
                invoices.append(invoice_row)
            if settlement_row is not None:
                settlements.append(settlement_row)
            ground_truth.append(gt)

    return payments, invoices, settlements, ground_truth


def write_csv(path, rows, fieldnames):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def main():
    parser = argparse.ArgumentParser(description="Generate FinControl AI synthetic dataset")
    parser.add_argument("--seed", type=int, default=42, help="Random seed (default: 42)")
    parser.add_argument("--outdir", type=str, default=os.path.join(os.path.dirname(__file__), "synthetic"))
    args = parser.parse_args()

    payments, invoices, settlements, ground_truth = make_records(seed=args.seed)

    write_csv(os.path.join(args.outdir, "payments.csv"), payments,
              ["payment_id", "transaction_id", "amount", "date", "method", "merchant", "status"])
    write_csv(os.path.join(args.outdir, "invoices.csv"), invoices,
              ["invoice_id", "transaction_id", "amount", "date", "merchant"])
    write_csv(os.path.join(args.outdir, "settlements.csv"), settlements,
              ["settlement_id", "transaction_id", "amount", "date", "fee_deducted", "merchant"])
    write_csv(os.path.join(args.outdir, "ground_truth.csv"), ground_truth,
              ["transaction_id", "category", "expected_status", "expected_exception_type",
               "expected_resolution", "ground_truth_reason"])

    total_tx = len(ground_truth)
    n_exceptions = sum(1 for g in ground_truth if g["expected_status"] == "EXCEPTION")
    print(f"Generated {total_tx} transactions (seed={args.seed})")
    print(f"  payments.csv:     {len(payments)} rows")
    print(f"  invoices.csv:     {len(invoices)} rows")
    print(f"  settlements.csv:  {len(settlements)} rows")
    print(f"  ground_truth.csv: {len(ground_truth)} rows")
    print(f"  -> {total_tx - n_exceptions} expected MATCHED, {n_exceptions} expected EXCEPTION")
    print(f"Output dir: {args.outdir}")


if __name__ == "__main__":
    main()
