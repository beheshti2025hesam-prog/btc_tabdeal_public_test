"""Append-only forward journal primitives.

The same append-only writer handles decision, paper-candidate and paper-outcome
records. It never mutates a prior decision; later outcomes are separate events.
"""
from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
import json
import os
import stat
from typing import Any, Iterator, Mapping

try:
    import fcntl
except ImportError:  # pragma: no cover - supported runtime is Linux
    fcntl = None

DECISIONS = {"LONG", "SHORT", "NO_TRADE"}
REQUIRED_FIELDS = {
    "event_id", "observed_at", "symbol", "timeframe", "decision",
    "evidence_source",
}
MAX_LINE_BYTES = 1024 * 1024


def _validate_decision_record(record: Mapping[str, Any]) -> None:
    missing = sorted(REQUIRED_FIELDS - set(record))
    if missing:
        raise ValueError(f"missing journal fields:{','.join(missing)}")
    if record["decision"] not in DECISIONS:
        raise ValueError("invalid decision")
    if not isinstance(record["event_id"], str) or not record["event_id"].strip():
        raise ValueError("event_id is required")
    if not isinstance(record["evidence_source"], (str, list, tuple)):
        raise ValueError("evidence_source is required")
    if record.get("outcome") is not None:
        raise ValueError("future outcome leakage: decision record must have outcome=None")
    if record.get("closed_at") is not None:
        raise ValueError("future outcome leakage: decision record must have closed_at=None")


class ForwardJournalV1:
    """Single-writer append-only JSONL writer with per-file process locking.

    Legacy rows without event_id remain readable for backward compatibility;
    every newly appended row must carry a unique, non-empty event_id.
    """

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.lock_path = self.path.with_name(self.path.name + ".lock")

    @contextmanager
    def _write_lock(self) -> Iterator[None]:
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        if self.lock_path.is_symlink():
            raise ValueError("journal lock path must not be a symlink")
        with self.lock_path.open("a+", encoding="utf-8") as lock_file:
            if fcntl is None:
                raise RuntimeError("atomic single-writer locking requires fcntl on the supported runtime")
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)

    def _ids(self) -> set[str]:
        if self.path.is_symlink():
            raise ValueError("journal path must not be a symlink")
        if not self.path.exists():
            return set()
        if not stat.S_ISREG(self.path.stat().st_mode):
            raise ValueError("journal path is not a regular file")

        ids: set[str] = set()
        with self.path.open("rb") as handle:
            line_number = 0
            while True:
                raw_line = handle.readline(MAX_LINE_BYTES + 1)
                if not raw_line:
                    break
                line_number += 1
                if len(raw_line) > MAX_LINE_BYTES:
                    raise ValueError(f"journal record size limit exceeded at line {line_number}")
                if not raw_line.endswith(b"\n"):
                    raise ValueError(f"journal has incomplete trailing record at line {line_number}")
                if raw_line in (b"\n", b"\r\n"):
                    raise ValueError(f"journal contains blank record at line {line_number}")
                try:
                    item = json.loads(raw_line.decode("utf-8", errors="strict"))
                except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                    raise ValueError(f"journal contains malformed JSON at line {line_number}") from exc
                if not isinstance(item, dict):
                    raise ValueError(f"journal record is not an object at line {line_number}")
                # A small number of pre-existing paper-ledger rows predate event_id.
                # Preserve them, but never create another unidentifiable row.
                if "event_id" not in item:
                    continue
                event_id = item["event_id"]
                if not isinstance(event_id, str) or not event_id.strip():
                    raise ValueError(f"journal record has invalid event_id at line {line_number}")
                if event_id in ids:
                    raise ValueError(f"journal contains duplicate event_id at line {line_number}")
                ids.add(event_id)
        return ids

    def append_event(self, record: Mapping[str, Any]) -> bool:
        """Append any immutable journal event; return False for an existing event_id."""
        if not isinstance(record, Mapping):
            raise ValueError("journal record must be a mapping")
        event_id = record.get("event_id")
        if not isinstance(event_id, str) or not event_id.strip():
            raise ValueError("event_id is required")

        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._write_lock():
            if event_id in self._ids():
                return False

            line = json.dumps(dict(record), ensure_ascii=False, sort_keys=True) + "\n"
            encoded = line.encode("utf-8")
            if len(encoded) > MAX_LINE_BYTES:
                raise ValueError("journal record size limit exceeded")
            with self.path.open("ab") as handle:
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
        return True

    def append_decision(self, record: Mapping[str, Any]) -> None:
        _validate_decision_record(record)
        payload = dict(record)
        payload.setdefault("outcome", None)
        payload.setdefault("closed_at", None)
        if not self.append_event(payload):
            raise ValueError("duplicate event_id")

    def append_outcome(self, *, event_id: str, outcome: str, closed_at: str) -> None:
        raise NotImplementedError(
            "Outcome mutation requires a separate immutable outcome artifact; "
            "do not rewrite the original decision record."
        )
