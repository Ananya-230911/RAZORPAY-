"""
FinControl AI - Reconciliation Engine
======================================
Module 2 of the pipeline. Pure pandas/Python. NO AI involved anywhere in
this file -- matching, amount comparison, date comparison and duplicate
detection must stay 100% deterministic so the numbers can be trusted.

Input:  data/synthetic/{payments,invoices,settlements}.csv
Output: one row per transaction_id with columns:
    transaction_id | status (MATCHED/EXCEPTION) | payment_amt |
    invoice_amt | settlement_amt | difference | records_present |
    date_gap_days | is_duplicate

Run directly for a quick sanity check:
    python reconciliation/matcher.py
"""

import os

import pandas as pd

AMOUNT_TOLERANCE = 0.01          # rupees; float-rounding slack only
DATE_TOLERANCE_DAYS = 3          # normal settlement window is T+2

DEFAULT_DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "synthetic")


def load_data(data_dir: str = DEFAULT_DATA_DIR):
    """Load the three source CSVs. Raises a clear error if any is missing/empty."""
    paths = {
        "payments": os.path.join(data_dir, "payments.csv"),
        "invoices": os.path.join(data_dir, "invoices.csv"),
        "settlements": os.path.join(data_dir, "settlements.csv"),
    }
    frames = {}
    for name, path in paths.items():
        if not os.path.exists(path):
            raise FileNotFoundError(
                f"Missing {name} file at {path}. Run `python data/generate_data.py` first."
            )
        df = pd.read_csv(path)
        if df.empty:
            raise ValueError(f"{name}.csv at {path} has no rows -- cannot reconcile an empty batch.")
        frames[name] = df
    return frames["payments"], frames["invoices"], frames["settlements"]


def _find_duplicate_transaction_ids(payments: pd.DataFrame) -> set:
    """
    Deterministic duplicate-charge detection: two payment records with the
    same amount, merchant, method and date are almost certainly the same
    charge submitted twice. Flags ALL transaction_ids in any such group.
    """
    if payments.empty:
        return set()
    key_cols = ["amount", "merchant", "method", "date"]
    dup_mask = payments.duplicated(subset=key_cols, keep=False)
    return set(payments.loc[dup_mask, "transaction_id"])


def reconcile(payments: pd.DataFrame, invoices: pd.DataFrame, settlements: pd.DataFrame) -> pd.DataFrame:
    """
    Outer-join the three sources on transaction_id and compute, per
    transaction: presence, amount difference, date gap, MATCHED/EXCEPTION
    status, and duplicate flag.
    """
    pay = payments.rename(columns={"amount": "payment_amt", "date": "payment_date"})[
        ["transaction_id", "payment_amt", "payment_date", "merchant", "method"]
    ]
    inv = invoices.rename(columns={"amount": "invoice_amt", "date": "invoice_date"})[
        ["transaction_id", "invoice_amt", "invoice_date"]
    ]
    stl = settlements.rename(columns={"amount": "settlement_amt", "date": "settlement_date"})[
        ["transaction_id", "settlement_amt", "settlement_date", "fee_deducted"]
    ]

    merged = pay.merge(inv, on="transaction_id", how="outer").merge(stl, on="transaction_id", how="outer")

    duplicate_ids = _find_duplicate_transaction_ids(payments)

    rows = []
    for _, r in merged.iterrows():
        has_pay = pd.notna(r["payment_amt"])
        has_inv = pd.notna(r["invoice_amt"])
        has_stl = pd.notna(r["settlement_amt"])

        present = []
        if has_pay:
            present.append("PAYMENT")
        if has_inv:
            present.append("INVOICE")
        if has_stl:
            present.append("SETTLEMENT")
        records_present = ",".join(present) if present else "NONE"

        # difference: prefer payment-vs-settlement (the actual cash gap);
        # fall back to payment-vs-invoice when settlement is absent.
        difference = None
        if has_pay and has_stl:
            difference = round(r["payment_amt"] - r["settlement_amt"], 2)
        elif has_pay and has_inv:
            difference = round(r["payment_amt"] - r["invoice_amt"], 2)

        date_gap_days = None
        if has_pay and has_stl:
            date_gap_days = (pd.to_datetime(r["settlement_date"]) - pd.to_datetime(r["payment_date"])).days

        is_duplicate = r["transaction_id"] in duplicate_ids

        all_present = has_pay and has_inv and has_stl
        amounts_agree = (
            has_pay and has_inv and has_stl
            and abs(r["payment_amt"] - r["invoice_amt"]) <= AMOUNT_TOLERANCE
            and abs(r["payment_amt"] - r["settlement_amt"]) <= AMOUNT_TOLERANCE
        )
        date_ok = date_gap_days is not None and abs(date_gap_days - 2) <= DATE_TOLERANCE_DAYS

        status = "MATCHED" if (all_present and amounts_agree and date_ok and not is_duplicate) else "EXCEPTION"

        rows.append({
            "transaction_id": r["transaction_id"],
            "status": status,
            "payment_amt": r["payment_amt"] if has_pay else None,
            "invoice_amt": r["invoice_amt"] if has_inv else None,
            "settlement_amt": r["settlement_amt"] if has_stl else None,
            "difference": difference,
            "records_present": records_present,
            "date_gap_days": date_gap_days,
            "is_duplicate": is_duplicate,
            "merchant": r["merchant"] if pd.notna(r.get("merchant")) else None,
        })

    result = pd.DataFrame(rows).sort_values("transaction_id").reset_index(drop=True)
    return result


def run(data_dir: str = DEFAULT_DATA_DIR) -> pd.DataFrame:
    payments, invoices, settlements = load_data(data_dir)
    return reconcile(payments, invoices, settlements)


if __name__ == "__main__":
    df = run()
    n_matched = (df["status"] == "MATCHED").sum()
    n_exception = (df["status"] == "EXCEPTION").sum()
    print(f"Reconciled {len(df)} transactions")
    print(f"  MATCHED:   {n_matched}")
    print(f"  EXCEPTION: {n_exception}")
    print(f"  Duplicates flagged: {df['is_duplicate'].sum()}")
    print()
    print(df.head(10).to_string(index=False))
