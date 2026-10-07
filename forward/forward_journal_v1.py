"""Append-only forward journal primitives.

Forward baseline hardening:
- single-writer lock around read/duplicate-check/append
- fail closed on malformed existing JSONL
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
        if not self.path.exists():
            return set()
        ids: set[str] = set()
        for line_number, line in enumerate(
            self.path.read_text(encoding="utf-8").splitlines(), start=1
        ):
            if not line.strip():
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"journal contains malformed JSON at line {line_number}") from exc
            event_id = item.get("event_id")
            if event_id:
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

            with self.path.open("a", encoding="utf-8") as f:
                f.write(line)
                f.flush()
                os.fsync(f.fileno())

    def append_outcome(self, *, event_id: str, outcome: str, closed_at: str) -> None:
        raise NotImplementedError(
            "Outcome mutation requires a separate immutable outcome artifact; "
            "do not rewrite the original decision record."
        )
