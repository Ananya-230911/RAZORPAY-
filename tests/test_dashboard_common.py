"""
Unit tests for app/common.py (Module 8+10 shared dashboard utilities).

Streamlit pages themselves need a running server to test meaningfully
(verified manually via Playwright against a live `streamlit run` during
development -- see the commit message for what was checked: all 6 pages
render without error, and the human-decision write path was exercised
end-to-end through the actual UI). This file covers the plain-Python
helpers that don't depend on the Streamlit runtime.

Run:
    pytest tests/test_dashboard_common.py -v
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.common import get_conn, load_results
from database.db import DEFAULT_DB_PATH
from evaluation.evaluate import RESULTS_PATH


def test_get_conn_returns_none_when_db_missing(tmp_path, monkeypatch):
    fake_path = str(tmp_path / "does_not_exist.db")
    monkeypatch.setattr("app.common.DEFAULT_DB_PATH", fake_path)
    assert get_conn() is None


def test_get_conn_returns_connection_when_db_exists(tmp_path, monkeypatch):
    from database.db import init_db

    db_path = str(tmp_path / "test.db")
    init_db(db_path).close()
    monkeypatch.setattr("app.common.DEFAULT_DB_PATH", db_path)
    conn = get_conn()
    assert conn is not None
    conn.close()


def test_load_results_returns_none_when_missing(tmp_path, monkeypatch):
    fake_path = str(tmp_path / "results.json")
    monkeypatch.setattr("app.common.RESULTS_PATH", fake_path)
    assert load_results() is None


def test_load_results_reads_real_json(tmp_path, monkeypatch):
    import json

    fake_path = str(tmp_path / "results.json")
    with open(fake_path, "w") as f:
        json.dump({"dataset": {"total_records": 91}}, f)
    monkeypatch.setattr("app.common.RESULTS_PATH", fake_path)
    results = load_results()
    assert results["dataset"]["total_records"] == 91
