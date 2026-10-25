from __future__ import annotations

import sqlite3

import pytest

from forward.execution_journal_view_v1 import (
    ExecutionJournalProjectionError,
    read_execution_journal,
)


def make_db(path, *, state="FILLED", observed_at="2026-10-25T10:00:00+00:00",
            quantity="0.25", average_price="100.5", raw_hash="b" * 64):
    db = sqlite3.connect(path)
    db.execute("""CREATE TABLE execution_orders (
        client_order_id TEXT PRIMARY KEY,
        decision_id TEXT NOT NULL UNIQUE,
        payload_sha256 TEXT NOT NULL,
        state TEXT NOT NULL,
        venue_order_id TEXT,
        reconciliation_ref TEXT,
        last_error_code TEXT,
        venue_status TEXT,
        executed_quantity TEXT,
        average_fill_price TEXT,
        raw_response_sha256 TEXT,
        observed_at TEXT,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )""")
    db.execute(
        """INSERT INTO execution_orders
        (client_order_id,decision_id,payload_sha256,state,venue_order_id,venue_status,
         executed_quantity,average_fill_price,raw_response_sha256,observed_at)
        VALUES(?,?,?,?,?,?,?,?,?,?)""",
        ("client-1", "decision-1", "a" * 64, state, "venue-1", "FILLED",
         quantity, average_price, raw_hash, observed_at),
    )
    db.commit()
    db.close()


def test_projects_verified_fill_without_inventing_costs_or_pnl(tmp_path):
    path = tmp_path / "execution.sqlite"
    make_db(path)
    before = path.read_bytes()
    result = read_execution_journal(path)
    assert result["status"] == "VERIFIED"
    assert result["read_only"] is True
    assert result["execution_enabled"] is False
    order = result["orders"][0]
    assert order["state"] == "FILLED"
    assert order["executed_quantity"] == "0.25"
    assert order["average_fill_price"] == "100.5"
    assert order["fees"] == order["funding"] == order["realized_pnl"] == "UNKNOWN"
    assert order["pnl_evidence"] == "NOT_LINKED"
    assert path.read_bytes() == before


def test_unknown_or_incomplete_fill_fails_closed(tmp_path):
    path = tmp_path / "execution.sqlite"
    make_db(path, quantity=None)
    with pytest.raises(ExecutionJournalProjectionError, match="fill_evidence_incomplete"):
        read_execution_journal(path)


def test_naive_fill_timestamp_fails_closed(tmp_path):
    path = tmp_path / "execution.sqlite"
    make_db(path, observed_at="2026-10-25T10:00:00")
    with pytest.raises(ExecutionJournalProjectionError, match="naive_observed_at"):
        read_execution_journal(path)


def test_bad_provenance_hash_fails_closed(tmp_path):
    path = tmp_path / "execution.sqlite"
    make_db(path, raw_hash="not-a-hash")
    with pytest.raises(ExecutionJournalProjectionError, match="invalid_raw_response_sha256"):
        read_execution_journal(path)


def test_read_only_connection_does_not_create_or_mutate_database(tmp_path):
    path = tmp_path / "execution.sqlite"
    make_db(path, state="ACKNOWLEDGED", quantity=None, average_price=None, raw_hash=None)
    before = path.read_bytes()
    read_execution_journal(path)
    assert path.read_bytes() == before


def test_sqlite_backup_restore_preserves_projection(tmp_path):
    source = tmp_path / "source.sqlite"
    backup = tmp_path / "backup.sqlite"
    restored = tmp_path / "restored.sqlite"
    make_db(source)
    src = sqlite3.connect(f"file:{source}?mode=ro", uri=True)
    dest = sqlite3.connect(backup)
    try:
        src.backup(dest)
    finally:
        dest.close()
        src.close()
    backup_db = sqlite3.connect(backup)
    restore_db = sqlite3.connect(restored)
    try:
        backup_db.backup(restore_db)
        restore_db.commit()
    finally:
        restore_db.close()
        backup_db.close()
    original = read_execution_journal(source)
    recovered = read_execution_journal(restored)
    assert original["orders"] == recovered["orders"]
    check = sqlite3.connect(f"file:{restored}?mode=ro", uri=True)
    try:
        assert check.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    finally:
        check.close()


def test_missing_or_incompatible_database_fails_closed(tmp_path):
    path = tmp_path / "wrong.sqlite"
    sqlite3.connect(path).close()
    with pytest.raises(ExecutionJournalProjectionError, match="execution_orders_table_missing"):
        read_execution_journal(path)
