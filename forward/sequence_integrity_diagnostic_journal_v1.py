"""Append-only, hash-chained diagnostics for fail-closed sequence anomalies."""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
from pathlib import Path
from typing import Any


class SequenceIntegrityDiagnosticJournalV1:
    """Persist safe conflict fingerprints; never repair the source stream or journal."""

    SCHEMA = "hes_sequence_integrity_diagnostic_journal_v1"

    def __init__(self, path: str | Path):
        self.path = Path(path)

    @staticmethod
    def _canonical(record: dict[str, Any]) -> bytes:
        return json.dumps(record, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")

    @classmethod
    def _verify_existing(cls, raw: bytes) -> tuple[int, str | None]:
        if not raw:
            return 0, None
        if not raw.endswith(b"\n"):
            raise RuntimeError("diagnostic journal has a partial trailing record; refusing append")
        count = 0
        previous_digest = None
        for line_number, line in enumerate(raw.splitlines(), start=1):
            try:
                record = json.loads(line.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise RuntimeError(f"diagnostic journal has invalid JSON at line {line_number}") from exc
            digest = record.pop("record_sha256", None)
            expected = hashlib.sha256(cls._canonical(record)).hexdigest()
            if digest != expected:
                raise RuntimeError(f"diagnostic journal hash mismatch at line {line_number}")
            if record.get("schema") != cls.SCHEMA:
                raise RuntimeError(f"diagnostic journal schema mismatch at line {line_number}")
            if record.get("previous_record_sha256") != previous_digest:
                raise RuntimeError(f"diagnostic journal hash-chain mismatch at line {line_number}")
            count += 1
            previous_digest = digest
        return count, previous_digest

    def append_blocked_run(
        self,
        *,
        run_id: str,
        observed_at_utc: str,
        reason: str,
        diagnostics: tuple[dict[str, Any], ...] | list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        events = [
            item for item in diagnostics
            if item.get("reason") is not None
            or item.get("status") in {"REJECT_STREAM", "ANOMALY"}
        ]
        if not events:
            return None

        self.path.parent.mkdir(parents=True, exist_ok=True)
        created = not self.path.exists()
        flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND
        fd = os.open(self.path, flags, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            existing = self.path.read_bytes() if self.path.exists() else b""
            count, previous_digest = self._verify_existing(existing)
            payload: dict[str, Any] = {
                "schema": self.SCHEMA,
                "record_number": count + 1,
                "run_id": run_id,
                "observed_at_utc": observed_at_utc,
                "status": "BLOCKED",
                "reason": reason,
                "sequence_events": events,
                "previous_record_sha256": previous_digest,
            }
            digest = hashlib.sha256(self._canonical(payload)).hexdigest()
            record = {**payload, "record_sha256": digest}
            encoded = self._canonical(record) + b"\n"
            view = memoryview(encoded)
            while view:
                written = os.write(fd, view)
                if written <= 0:
                    raise OSError("short write to diagnostic journal")
                view = view[written:]
            os.fsync(fd)
            if created:
                directory_fd = os.open(self.path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
                try:
                    os.fsync(directory_fd)
                finally:
                    os.close(directory_fd)
            return record
        finally:
            try:
                fcntl.flock(fd, fcntl.LOCK_UN)
            finally:
                os.close(fd)
