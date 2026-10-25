from __future__ import annotations

import json
import sqlite3

import pytest

from forward.sqlite_backup_v1 import (
    SQLiteBackupError,
    create_verified_backup,
    restore_verified_backup,
)


def create_db(path):
    db = sqlite3.connect(path)
    db.execute("CREATE TABLE execution_orders (client_order_id TEXT PRIMARY KEY, state TEXT NOT NULL)")
    db.execute("INSERT INTO execution_orders VALUES ('client-1', 'FILLED')")
    db.commit()
    db.close()


def test_verified_backup_restore_preserves_data_and_integrity(tmp_path):
    source = tmp_path / "execution.sqlite"
    backup = tmp_path / "execution.sqlite.backup"
    restored = tmp_path / "restored.sqlite"
    create_db(source)
    original_bytes = source.read_bytes()
    manifest = create_verified_backup(source, backup)
    assert manifest["integrity_check"] == "ok"
    assert manifest["backup_sha256"]
    assert source.read_bytes() == original_bytes
    result = restore_verified_backup(backup, restored)
    assert result["status"] == "VERIFIED"
    db = sqlite3.connect(f"file:{restored}?mode=ro", uri=True)
    try:
        assert db.execute("SELECT * FROM execution_orders").fetchall() == [("client-1", "FILLED")]
        assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    finally:
        db.close()


def test_backup_refuses_overwrite_and_restore_requires_explicit_overwrite(tmp_path):
    source = tmp_path / "source.sqlite"
    backup = tmp_path / "backup.sqlite"
    destination = tmp_path / "destination.sqlite"
    create_db(source)
    create_verified_backup(source, backup)
    with pytest.raises(SQLiteBackupError, match="backup_destination_already_exists"):
        create_verified_backup(source, backup)
    create_db(destination)
    with pytest.raises(SQLiteBackupError, match="restore_destination_exists"):
        restore_verified_backup(backup, destination)
    result = restore_verified_backup(backup, destination, overwrite=True)
    assert result["status"] == "VERIFIED"


def test_tampered_backup_fails_before_restore(tmp_path):
    source = tmp_path / "source.sqlite"
    backup = tmp_path / "backup.sqlite"
    destination = tmp_path / "destination.sqlite"
    create_db(source)
    create_verified_backup(source, backup)
    backup.write_bytes(backup.read_bytes() + b"tamper")
    with pytest.raises(SQLiteBackupError, match="backup_digest_mismatch"):
        restore_verified_backup(backup, destination)
    assert not destination.exists()


def test_manifest_corruption_fails_closed(tmp_path):
    source = tmp_path / "source.sqlite"
    backup = tmp_path / "backup.sqlite"
    create_db(source)
    create_verified_backup(source, backup)
    (tmp_path / "backup.sqlite.manifest.json").write_text(json.dumps({"schema": "wrong"}))
    with pytest.raises(SQLiteBackupError, match="backup_manifest_schema_invalid"):
        restore_verified_backup(backup, tmp_path / "restored.sqlite")


def test_missing_source_fails_closed(tmp_path):
    with pytest.raises(SQLiteBackupError, match="source_database_missing_or_unsafe"):
        create_verified_backup(tmp_path / "missing.sqlite", tmp_path / "backup.sqlite")


def test_operator_cli_backup_and_restore(tmp_path, capsys):
    from scripts.backup_execution_journal_v1 import main

    source = tmp_path / "source.sqlite"
    backup = tmp_path / "backup.sqlite"
    restored = tmp_path / "restored.sqlite"
    create_db(source)
    assert main(["--backup", str(source), str(backup)]) == 0
    assert json.loads(capsys.readouterr().out)["integrity_check"] == "ok"
    assert main(["--restore", str(backup), str(restored)]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "VERIFIED"
