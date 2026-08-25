"""
FinControl AI - Storage + Audit Log
======================================
Module 7 of the pipeline. SQLite, file-based, zero setup. Every write to
`transactions`, `investigations`, or `human_decisions` also appends a row
to `audit_log` -- timestamp, actor (system/AI/human), action, and an
evidence reference -- so the dashboard's Audit Log page (Module 10) has a
complete, honest trail of what happened and who/what did it.

No real money moves through this file. Every human action recorded here
is explicitly a SIMULATED decision (see app/dashboard.py).

Run directly to (re)initialize an empty database:
    python -m database.db
"""

import json
import os
import sqlite3
from datetime import datetime, timezone

import pandas as pd

DEFAULT_DB_PATH = os.path.join(os.path.dirname(__file__), "..", "fincontrol.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS transactions (
    transaction_id      TEXT PRIMARY KEY,
    status               TEXT NOT NULL,
    exception_type        TEXT,
    payment_amt           REAL,
    invoice_amt            REAL,
    settlement_amt         REAL,
    difference             REAL,
    records_present        TEXT,
    date_gap_days          REAL,
    is_duplicate            INTEGER,
    merchant                TEXT,
    updated_at               TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS investigations (
    transaction_id      TEXT PRIMARY KEY,
    probable_cause        TEXT,
    evidence_used          TEXT,      -- JSON-encoded list
    confidence              REAL,
    recommendation          TEXT,
    ai_status                TEXT,     -- RESOLVED / UNRESOLVED (from Module 5)
    decision                 TEXT,     -- AUTO_SUGGESTED / NEEDS_HUMAN_REVIEW (from Module 6)
    updated_at                TEXT NOT NULL,
    FOREIGN KEY (transaction_id) REFERENCES transactions (transaction_id)
);

CREATE TABLE IF NOT EXISTS human_decisions (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    transaction_id      TEXT NOT NULL,
    action                 TEXT NOT NULL,   -- APPROVE / REJECT / MARK_UNRESOLVED
    note                    TEXT,
    actor                    TEXT NOT NULL,
    created_at               TEXT NOT NULL,
    FOREIGN KEY (transaction_id) REFERENCES transactions (transaction_id)
);

CREATE TABLE IF NOT EXISTS audit_log (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp     TEXT NOT NULL,
    actor          TEXT NOT NULL,   -- system / AI / human
    action          TEXT NOT NULL,
    transaction_id TEXT,
    details          TEXT,           -- JSON-encoded
    evidence_ref     TEXT
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_connection(db_path: str = DEFAULT_DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(db_path: str = DEFAULT_DB_PATH) -> sqlite3.Connection:
    conn = get_connection(db_path)
    conn.executescript(SCHEMA)
    conn.commit()
    return conn


def _log_audit(conn, actor: str, action: str, transaction_id: str = None,
                details: dict = None, evidence_ref: str = None):
    conn.execute(
        "INSERT INTO audit_log (timestamp, actor, action, transaction_id, details, evidence_ref) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (_now(), actor, action, transaction_id, json.dumps(details) if details else None, evidence_ref),
    )


def write_transactions(conn: sqlite3.Connection, classified_df: pd.DataFrame):
    """Module 2+3 output -> `transactions` table, one audit_log entry per run."""
    now = _now()
    rows = classified_df.to_dict("records")
    for r in rows:
        conn.execute(
            """INSERT INTO transactions
               (transaction_id, status, exception_type, payment_amt, invoice_amt,
                settlement_amt, difference, records_present, date_gap_days,
                is_duplicate, merchant, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(transaction_id) DO UPDATE SET
                 status=excluded.status, exception_type=excluded.exception_type,
                 payment_amt=excluded.payment_amt, invoice_amt=excluded.invoice_amt,
                 settlement_amt=excluded.settlement_amt, difference=excluded.difference,
                 records_present=excluded.records_present, date_gap_days=excluded.date_gap_days,
                 is_duplicate=excluded.is_duplicate, merchant=excluded.merchant,
                 updated_at=excluded.updated_at""",
            (r["transaction_id"], r["status"], r.get("exception_type"), r.get("payment_amt"),
             r.get("invoice_amt"), r.get("settlement_amt"), r.get("difference"),
             r.get("records_present"), r.get("date_gap_days"),
             int(bool(r.get("is_duplicate"))), r.get("merchant"), now),
        )
    _log_audit(conn, actor="system", action="RECONCILE_AND_CLASSIFY",
               details={"row_count": len(rows)})
    conn.commit()


def write_investigations(conn: sqlite3.Connection, decided_results: list):
    """Module 5+6 output -> `investigations` table, one audit_log entry per row
    (citing the evidence actually used, per transaction, for a real trail)."""
    now = _now()
    for r in decided_results:
        conn.execute(
            """INSERT INTO investigations
               (transaction_id, probable_cause, evidence_used, confidence,
                recommendation, ai_status, decision, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(transaction_id) DO UPDATE SET
                 probable_cause=excluded.probable_cause, evidence_used=excluded.evidence_used,
                 confidence=excluded.confidence, recommendation=excluded.recommendation,
                 ai_status=excluded.ai_status, decision=excluded.decision,
                 updated_at=excluded.updated_at""",
            (r["transaction_id"], r.get("probable_cause"), json.dumps(r.get("evidence_used", [])),
             r.get("confidence"), r.get("recommendation"), r.get("status"), r.get("decision"), now),
        )
        _log_audit(
            conn, actor="AI", action="INVESTIGATE", transaction_id=r["transaction_id"],
            details={"status": r.get("status"), "decision": r.get("decision"), "confidence": r.get("confidence")},
            evidence_ref=", ".join(r.get("evidence_used", [])) or None,
        )
    conn.commit()


def record_human_decision(conn: sqlite3.Connection, transaction_id: str, action: str,
                            note: str = "", actor: str = "human"):
    """
    Record a human's SIMULATED decision on an exception (Module 8's write
    path). `action` is one of APPROVE / REJECT / MARK_UNRESOLVED (dashboard
    enforces the choice set; this layer just persists + audits it).
    """
    now = _now()
    conn.execute(
        "INSERT INTO human_decisions (transaction_id, action, note, actor, created_at) VALUES (?, ?, ?, ?, ?)",
        (transaction_id, action, note, actor, now),
    )
    _log_audit(conn, actor=actor, action=f"HUMAN_{action}", transaction_id=transaction_id,
               details={"note": note})
    conn.commit()


def get_transactions(conn: sqlite3.Connection) -> pd.DataFrame:
    return pd.read_sql_query("SELECT * FROM transactions ORDER BY transaction_id", conn)


def get_investigations(conn: sqlite3.Connection) -> pd.DataFrame:
    df = pd.read_sql_query("SELECT * FROM investigations", conn)
    if not df.empty:
        df["evidence_used"] = df["evidence_used"].apply(lambda x: json.loads(x) if x else [])
    return df


def get_human_decisions(conn: sqlite3.Connection) -> pd.DataFrame:
    return pd.read_sql_query("SELECT * FROM human_decisions ORDER BY created_at DESC", conn)


def get_audit_log(conn: sqlite3.Connection) -> pd.DataFrame:
    return pd.read_sql_query("SELECT * FROM audit_log ORDER BY id DESC", conn)


def get_full_case(conn: sqlite3.Connection, transaction_id: str) -> dict:
    """Everything known about one transaction: reconciliation + investigation
    + human decisions -- what app/pages/3_investigation.py renders."""
    tx = conn.execute("SELECT * FROM transactions WHERE transaction_id = ?", (transaction_id,)).fetchone()
    inv = conn.execute("SELECT * FROM investigations WHERE transaction_id = ?", (transaction_id,)).fetchone()
    decisions = conn.execute(
        "SELECT * FROM human_decisions WHERE transaction_id = ? ORDER BY created_at", (transaction_id,)
    ).fetchall()
    return {
        "transaction": dict(tx) if tx else None,
        "investigation": ({**dict(inv), "evidence_used": json.loads(inv["evidence_used"] or "[]")} if inv else None),
        "human_decisions": [dict(d) for d in decisions],
    }


if __name__ == "__main__":
    conn = init_db()
    print(f"Initialized database at {DEFAULT_DB_PATH}")
    print("Tables:", [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")])
    conn.close()
