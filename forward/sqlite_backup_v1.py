"""Verified, dependency-free SQLite backup/restore for the existing execution journal.

This is an operator utility, not a scheduler. It never contacts a venue or
changes the source database. Restore refuses to overwrite an existing target
unless the caller explicitly opts in.
"""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import sqlite3
import tempfile
from typing import Any
from urllib.parse import quote


class SQLiteBackupError(ValueError):
    """Backup/restore failed verification and must not be used."""


def _regular_file(path: Path, code: str) -> None:
    if path.is_symlink() or not path.is_file():
        raise SQLiteBackupError(code)


def _hash_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _integrity(path: Path) -> None:
    uri = "file:" + quote(str(path.resolve()), safe="/:") + "?mode=ro"
    try:
        db = sqlite3.connect(uri, uri=True, timeout=3.0)
        try:
            row = db.execute("PRAGMA integrity_check").fetchone()
            if not row or row[0] != "ok":
                raise SQLiteBackupError("sqlite_integrity_check_failed")
        finally:
            db.close()
    except SQLiteBackupError:
        raise
    except sqlite3.Error as exc:
        raise SQLiteBackupError("sqlite_database_unreadable") from exc


def create_verified_backup(source: str | Path, destination: str | Path) -> dict[str, Any]:
    source_path, destination_path = Path(source), Path(destination)
    _regular_file(source_path, "source_database_missing_or_unsafe")
    if destination_path.exists() or destination_path.is_symlink():
        raise SQLiteBackupError("backup_destination_already_exists")
    if source_path.resolve() == destination_path.resolve():
        raise SQLiteBackupError("backup_source_equals_destination")
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    _integrity(source_path)
    fd, temporary_name = tempfile.mkstemp(prefix=".hes-backup-", suffix=".sqlite", dir=destination_path.parent)
    os.close(fd)
    temporary = Path(temporary_name)
    try:
        src_uri = "file:" + quote(str(source_path.resolve()), safe="/:") + "?mode=ro"
        src = sqlite3.connect(src_uri, uri=True, timeout=3.0)
        dst = sqlite3.connect(temporary)
        try:
            src.backup(dst)
            dst.commit()
        finally:
            dst.close()
            src.close()
        _integrity(temporary)
        backup_hash = _hash_file(temporary)
        os.replace(temporary, destination_path)
        manifest = {
            "schema": "hes.sqlite_backup_manifest.v1",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "source_name": source_path.name,
            "backup_name": destination_path.name,
            "backup_sha256": backup_hash,
            "backup_size_bytes": destination_path.stat().st_size,
            "integrity_check": "ok",
        }
        manifest_path = Path(str(destination_path) + ".manifest.json")
        manifest_tmp = Path(str(manifest_path) + ".tmp")
        manifest_tmp.write_text(json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
        os.replace(manifest_tmp, manifest_path)
        return manifest
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def restore_verified_backup(
    backup: str | Path,
    destination: str | Path,
    *,
    overwrite: bool = False,
) -> dict[str, Any]:
    backup_path, destination_path = Path(backup), Path(destination)
    manifest_path = Path(str(backup_path) + ".manifest.json")
    _regular_file(backup_path, "backup_missing_or_unsafe")
    _regular_file(manifest_path, "backup_manifest_missing_or_unsafe")
    if destination_path.exists() and not overwrite:
        raise SQLiteBackupError("restore_destination_exists")
    if destination_path.is_symlink():
        raise SQLiteBackupError("restore_destination_unsafe")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SQLiteBackupError("backup_manifest_invalid") from exc
    if not isinstance(manifest, dict) or manifest.get("schema") != "hes.sqlite_backup_manifest.v1":
        raise SQLiteBackupError("backup_manifest_schema_invalid")
    if manifest.get("backup_name") != backup_path.name or manifest.get("backup_sha256") != _hash_file(backup_path):
        raise SQLiteBackupError("backup_digest_mismatch")
    if manifest.get("backup_size_bytes") != backup_path.stat().st_size:
        raise SQLiteBackupError("backup_size_mismatch")
    _integrity(backup_path)
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=".hes-restore-", suffix=".sqlite", dir=destination_path.parent)
    os.close(fd)
    temporary = Path(temporary_name)
    try:
        src_uri = "file:" + quote(str(backup_path.resolve()), safe="/:") + "?mode=ro"
        src = sqlite3.connect(src_uri, uri=True, timeout=3.0)
        dst = sqlite3.connect(temporary)
        try:
            src.backup(dst)
            dst.commit()
        finally:
            dst.close()
            src.close()
        _integrity(temporary)
        restored_hash = _hash_file(temporary)
        os.replace(temporary, destination_path)
        return {
            "schema": "hes.sqlite_restore_result.v1",
            "status": "VERIFIED",
            "backup_sha256": manifest["backup_sha256"],
            "restored_database_sha256": restored_hash,
            "integrity_check": "ok",
        }
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
