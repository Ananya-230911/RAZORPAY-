"""
FinControl AI - Evaluation
===========================
Module 9 of the pipeline. Compares the system's output to
data/synthetic/ground_truth.csv and computes real, honest metrics.
Never hand-write a metric -- every number in the dashboard/README must
trace back to evaluation/results.json produced here.

v1 (this file, first pass): runs matcher + classifier only and reports
reconciliation match rate, exception-detection precision/recall/F1, false
positive rate, and exception-type accuracy. AI-resolution metrics
(Module 5/6 output) are added once the investigation agent exists --
run with --with-ai (or pass ai_results to evaluate()) once Module 5/6
are wired up; until then those fields are reported as null/"N/A".

Run directly:
    python -m evaluation.evaluate
"""

import argparse
import json
import os
import time

import pandas as pd

from reconciliation.classifier import classify
from reconciliation.matcher import DEFAULT_DATA_DIR, run as run_matcher

RESULTS_PATH = os.path.join(os.path.dirname(__file__), "results.json")


def _prf1(tp, fp, fn):
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return round(precision, 4), round(recall, 4), round(f1, 4)


def evaluate(classified: pd.DataFrame, ground_truth: pd.DataFrame,
             ai_results: pd.DataFrame = None, elapsed_seconds: float = None) -> dict:
    """
    Compute reconciliation + exception-detection + (optionally) AI-resolution
    metrics. `classified` is matcher.py + classifier.py output. `ai_results`
    is optional Module 5/6 output (transaction_id, status, confidence,
    decision, probable_cause) -- once wired up, adds AI-resolution accuracy,
    false-auto-resolve rate, and system-vs-truth UNRESOLVED counts.
    """
    df = classified.merge(ground_truth, on="transaction_id", how="inner", validate="one_to_one")
    total = len(df)

    match_rate = round((df["status"] == df["expected_status"]).mean(), 4)

    predicted_exc = df["status"] == "EXCEPTION"
    actual_exc = df["expected_status"] == "EXCEPTION"
    tp = int((predicted_exc & actual_exc).sum())
    fp = int((predicted_exc & ~actual_exc).sum())
    fn = int((~predicted_exc & actual_exc).sum())
    tn = int((~predicted_exc & ~actual_exc).sum())
    precision, recall, f1 = _prf1(tp, fp, fn)
    false_positive_rate = round(fp / (fp + tn), 4) if (fp + tn) else 0.0

    exc_rows = df[actual_exc]
    type_correct = int((exc_rows["exception_type"] == exc_rows["expected_exception_type"]).sum())
    exception_type_accuracy = round(type_correct / len(exc_rows), 4) if len(exc_rows) else 0.0

    results = {
        "dataset": {
            "total_records": total,
            "expected_matched": int((~actual_exc).sum()),
            "expected_exceptions": int(actual_exc.sum()),
        },
        "reconciliation": {
            "match_rate": match_rate,
            "true_positives_exceptions": tp,
            "false_positives_exceptions": fp,
            "false_negatives_exceptions": fn,
            "true_negatives_matched": tn,
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "false_positive_rate": false_positive_rate,
        },
        "classification": {
            "exception_type_accuracy": exception_type_accuracy,
            "exception_type_correct": type_correct,
            "exception_type_total": len(exc_rows),
        },
        "ai_resolution": None,
        "throughput": {
            "elapsed_seconds": round(elapsed_seconds, 4) if elapsed_seconds is not None else None,
            "records_per_second": round(total / elapsed_seconds, 2) if elapsed_seconds else None,
        },
    }

    if ai_results is not None:
        ai_df = df.merge(ai_results, on="transaction_id", how="left", suffixes=("", "_ai"))
        resolved = ai_df[ai_df["ai_status"] == "RESOLVED"]
        resolution_correct = 0
        for _, r in resolved.iterrows():
            # "correct" = the AI's own exception_type classification (from
            # Module 3, which fed it) matches ground truth's expected cause.
            if r["exception_type"] == r["expected_exception_type"]:
                resolution_correct += 1
        ai_resolution_accuracy = round(resolution_correct / len(resolved), 4) if len(resolved) else 0.0

        system_unresolved = int((ai_df["ai_status"] == "UNRESOLVED").sum())
        true_unresolved = int((ai_df["expected_resolution"] == "UNRESOLVED").sum())

        # False auto-resolve: AI said RESOLVED with high confidence but got
        # the cause wrong -- the dangerous case this whole system exists to prevent.
        false_auto_resolve = int(
            ((ai_df["ai_status"] == "RESOLVED") & (ai_df["exception_type"] != ai_df["expected_exception_type"])).sum()
        )

        results["ai_resolution"] = {
            "resolved_count": len(resolved),
            "resolution_accuracy": ai_resolution_accuracy,
            "system_unresolved_count": system_unresolved,
            "true_unresolved_count": true_unresolved,
            "false_auto_resolve_count": false_auto_resolve,
        }

    return results


def run(data_dir: str = DEFAULT_DATA_DIR, ai_results: pd.DataFrame = None) -> dict:
    start = time.perf_counter()
    reconciled = run_matcher(data_dir)
    classified = classify(reconciled)
    elapsed = time.perf_counter() - start

    ground_truth = pd.read_csv(os.path.join(data_dir, "ground_truth.csv"))
    results = evaluate(classified, ground_truth, ai_results=ai_results, elapsed_seconds=elapsed)

    os.makedirs(os.path.dirname(RESULTS_PATH), exist_ok=True)
    with open(RESULTS_PATH, "w") as f:
        json.dump(results, f, indent=2)

    return results


def print_report(results: dict):
    d, r, c, t = results["dataset"], results["reconciliation"], results["classification"], results["throughput"]
    print("=" * 60)
    print("FinControl AI - Evaluation Report")
    print("=" * 60)
    print(f"Records:                 {d['total_records']} "
          f"({d['expected_matched']} expected matched, {d['expected_exceptions']} expected exceptions)")
    print(f"Reconciliation match rate: {r['match_rate']:.2%}")
    print(f"Exception detection:     precision={r['precision']:.2%}  recall={r['recall']:.2%}  f1={r['f1']:.2%}")
    print(f"False positive rate:     {r['false_positive_rate']:.2%}")
    print(f"Exception-type accuracy: {c['exception_type_accuracy']:.2%} "
          f"({c['exception_type_correct']}/{c['exception_type_total']})")
    if results["ai_resolution"]:
        a = results["ai_resolution"]
        print("-" * 60)
        print(f"AI resolved:             {a['resolved_count']}")
        print(f"AI resolution accuracy:  {a['resolution_accuracy']:.2%}")
        print(f"Unresolved (system/true): {a['system_unresolved_count']} / {a['true_unresolved_count']}")
        print(f"False auto-resolves:     {a['false_auto_resolve_count']}")
    else:
        print("-" * 60)
        print("AI resolution: N/A (run with investigator+decision output; see evaluate.py --with-ai)")
    if t["records_per_second"]:
        print("-" * 60)
        print(f"Throughput:              {t['records_per_second']} records/sec "
              f"({t['elapsed_seconds']}s total)")
    print("=" * 60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Evaluate FinControl AI against ground truth")
    parser.add_argument("--data-dir", default=DEFAULT_DATA_DIR)
    args = parser.parse_args()

    results = run(args.data_dir)
    print_report(results)
    print(f"\nFull report written to {RESULTS_PATH}")
