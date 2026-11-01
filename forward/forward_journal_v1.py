"""Append-only forward journal primitives.

Forward baseline hardening:
- single-writer lock around read/duplicate-check/append
- fail closed on malformed, partial, or ambiguous existing JSONL
- bounded record size and strict event identity validation
- fsync after append
- decision records never accept future outcomes
"""
from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
import json
import os
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
    if not isinstance(record["event_id"], str) or not record["event_id"]:
        raise ValueError("event_id is required")
    if not isinstance(record["evidence_source"], (str, list, tuple)):
        raise ValueError("evidence_source is required")
    if "outcome" in record and record["outcome"] is not None:
        raise ValueError("future outcome leakage: decision record must have outcome=None")
    if "closed_at" in record and record["closed_at"] is not None:
        raise ValueError("future outcome leakage: decision record must have closed_at=None")


class ForwardJournalV1:
    """Single-writer append-only decision journal.

    The lock covers the complete check-and-append critical section, so two
    writers cannot both pass the duplicate check for the same event_id.
    Existing records are fully validated before a new append is allowed.
    """

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.lock_path = self.path.with_name(self.path.name + ".lock")

    @contextmanager
    def _write_lock(self) -> Iterator[None]:
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
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
        if not self.path.is_file():
            raise ValueError("journal path is not a regular file")

        ids: set[str] = set()
        with self.path.open("rb") as handle:
            for line_number, raw_line in enumerate(handle, start=1):
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
                event_id = item.get("event_id")
                if not isinstance(event_id, str) or not event_id.strip():
                    raise ValueError(f"journal record missing valid event_id at line {line_number}")
                if event_id in ids:
                    raise ValueError(f"journal contains duplicate event_id at line {line_number}")
                ids.add(event_id)
        return ids

    def append_decision(self, record: Mapping[str, Any]) -> None:
        _validate_decision_record(record)

        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._write_lock():
            if record["event_id"] in self._ids():
                raise ValueError("duplicate event_id")

            payload = dict(record)
            payload.setdefault("outcome", None)
            payload.setdefault("closed_at", None)
            line = json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n"
            if len(line.encode("utf-8")) > MAX_LINE_BYTES:
                raise ValueError("journal record size limit exceeded")

            with self.path.open("a", encoding="utf-8") as f:
                f.write(line)
                f.flush()
                os.fsync(f.fileno())

    def append_outcome(self, *, event_id: str, outcome: str, closed_at: str) -> None:
        raise NotImplementedError(
            "Outcome mutation requires a separate immutable outcome artifact; "
            "do not rewrite the original decision record."
        )
