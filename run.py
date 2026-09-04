#!/usr/bin/env python3
"""
FinControl AI - End-to-End Pipeline
======================================
One command that runs the whole system: generate -> reconcile -> classify
-> investigate (AI, if a key is configured) -> decide -> store -> evaluate
-> (optionally) launch the dashboard.

Usage:
    python run.py                    # full run, launches dashboard at the end
    python run.py --skip-ai          # skip Module 5/6 even if a key is set
    python run.py --skip-dashboard   # run the pipeline, print the report, exit
    python run.py --seed 7           # regenerate the synthetic dataset first

If GROQ_API_KEY isn't set and --skip-ai wasn't passed, the pipeline
does NOT crash -- it prints a clear message, skips Module 5/6, and still
populates the database and dashboard with reconciliation + classification
results (v1 metrics). See docs/FAILURES.md for why this matters.
"""

import argparse
import os
import subprocess
import sys

from dotenv import load_dotenv

load_dotenv()

from agents.decision import decide_all
from agents.investigator import MissingAPIKeyError, investigate_all
from database.db import init_db, write_investigations, write_transactions
from evaluation.evaluate import evaluate, print_report, RESULTS_PATH
from reconciliation.classifier import classify
from reconciliation.matcher import DEFAULT_DATA_DIR, run as run_matcher

import json
import time

import pandas as pd


def generate_data(seed: int):
    print(f"[1/6] Generating synthetic dataset (seed={seed})...")
    subprocess.run([sys.executable, os.path.join(os.path.dirname(__file__), "data", "generate_data.py"),
                     "--seed", str(seed)], check=True)


def reconcile_and_classify(data_dir: str):
    print("[2/6] Reconciling + classifying...")
    classified = classify(run_matcher(data_dir))
    n_matched = (classified["status"] == "MATCHED").sum()
    n_exception = (classified["status"] == "EXCEPTION").sum()
    print(f"      {len(classified)} transactions: {n_matched} MATCHED, {n_exception} EXCEPTION")
    return classified


def investigate_and_decide(classified: pd.DataFrame, skip_ai: bool):
    exception_rows = classified[classified["status"] == "EXCEPTION"].to_dict("records")
    if skip_ai:
        print("[3/6] Skipping AI investigation (--skip-ai passed).")
        return None
    if not os.environ.get("GROQ_API_KEY"):
        print("[3/6] Skipping AI investigation: GROQ_API_KEY is not set.")
        print("      Copy .env.example to .env and add a key to enable Module 5/6.")
        print("      The dashboard will still show all reconciliation/classification results.")
        return None

    print(f"[3/6] Investigating {len(exception_rows)} exceptions with Groq...")
    try:
        investigated = investigate_all(exception_rows)
    except MissingAPIKeyError as e:
        print(f"      {e}")
        return None
    decided = decide_all(investigated)
    n_auto = sum(1 for r in decided if r["decision"] == "AUTO_SUGGESTED")
    print(f"      {len(decided)} investigated: {n_auto} AUTO_SUGGESTED, {len(decided) - n_auto} NEEDS_HUMAN_REVIEW")
    return decided


def store(classified: pd.DataFrame, decided, db_path: str = None):
    print("[4/6] Writing to database...")
    kwargs = {"db_path": db_path} if db_path else {}
    conn = init_db(**kwargs)
    write_transactions(conn, classified)
    if decided:
        write_investigations(conn, decided)
    conn.close()
    print(f"      Database updated.")


def run_evaluation(classified: pd.DataFrame, decided, data_dir: str, elapsed_seconds: float):
    print("[5/6] Evaluating against ground truth...")
    ground_truth = pd.read_csv(os.path.join(data_dir, "ground_truth.csv"))
    ai_results = None
    if decided:
        ai_results = pd.DataFrame(decided).rename(columns={"status": "ai_status"})
    results = evaluate(classified, ground_truth, ai_results=ai_results, elapsed_seconds=elapsed_seconds)
    os.makedirs(os.path.dirname(RESULTS_PATH), exist_ok=True)
    with open(RESULTS_PATH, "w") as f:
        json.dump(results, f, indent=2)
    print_report(results)
    return results


def launch_dashboard():
    print("[6/6] Launching dashboard (Ctrl+C to stop)...")
    dashboard_path = os.path.join(os.path.dirname(__file__), "app", "dashboard.py")
    subprocess.run(["streamlit", "run", dashboard_path])


def main():
    parser = argparse.ArgumentParser(description="Run the full FinControl AI pipeline")
    parser.add_argument("--seed", type=int, default=None, help="Regenerate synthetic data with this seed first")
    parser.add_argument("--data-dir", default=DEFAULT_DATA_DIR)
    parser.add_argument("--db-path", default=None)
    parser.add_argument("--skip-ai", action="store_true", help="Skip Module 5/6 (AI investigation) even if a key is set")
    parser.add_argument("--skip-dashboard", action="store_true", help="Run the pipeline and exit without launching Streamlit")
    args = parser.parse_args()

    start = time.perf_counter()

    if args.seed is not None:
        generate_data(args.seed)

    classified = reconcile_and_classify(args.data_dir)
    decided = investigate_and_decide(classified, args.skip_ai)
    store(classified, decided, args.db_path)
    elapsed = time.perf_counter() - start
    run_evaluation(classified, decided, args.data_dir, elapsed)

    if not args.skip_dashboard:
        launch_dashboard()


if __name__ == "__main__":
    main()
