"""Read-only, fail-closed projection of the existing forward decision journal.

This is a view over the canonical immutable decision log, not a second journal.
Execution and realized outcomes are intentionally not inferred from decisions.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
from typing import Any, Iterator

from .forward_observation_writer_v1 import observation_digest

MAX_LINE_BYTES = 1024 * 1024
MAX_ROWS = 100
_ALLOWED_DECISIONS = {"LONG", "SHORT", "NO_TRADE"}


class JournalProjectionError(ValueError):
    """The canonical journal cannot safely be projected to the UI."""


def _iter_raw_lines(path: Path) -> Iterator[tuple[int, bytes]]:
    with path.open("rb") as handle:
        line_no = 0
        while True:
            raw_line = handle.readline(MAX_LINE_BYTES + 1)
            if not raw_line:
                return
            line_no += 1
            if len(raw_line) > MAX_LINE_BYTES:
                raise JournalProjectionError(f"record_size_limit_exceeded:{line_no}")
            yield line_no, raw_line


def read_decision_journal(path: str | Path, *, limit: int = 50, now: datetime | None = None) -> dict[str, Any]:
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= MAX_ROWS:
        raise JournalProjectionError("invalid_limit")
    file_path = Path(path)
    try:
        if file_path.is_symlink() or not file_path.is_file():
            raise JournalProjectionError("journal_not_a_regular_file")
        size = file_path.stat().st_size
        if size == 0:
            return {"schema": "hes.trade_journal_view.v1", "status": "EMPTY", "count": 0, "events": []}
        with file_path.open("rb") as handle:
            handle.seek(-1, 2)
            if handle.read(1) != b"\n":
                raise JournalProjectionError("partial_trailing_record")
    except JournalProjectionError:
        raise
    except OSError as exc:
        raise JournalProjectionError("journal_unavailable") from exc

    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None or current.utcoffset() is None:
        raise JournalProjectionError("verifier_clock_not_timezone_aware")
    events: list[dict[str, Any]] = []
    seen: dict[str, str] = {}
    total_records = 0
    try:
        for line_no, raw_line in _iter_raw_lines(file_path):
            try:
                line = raw_line.decode("utf-8", errors="strict").rstrip("\r\n")
            except UnicodeDecodeError as exc:
                raise JournalProjectionError(f"invalid_utf8:{line_no}") from exc
            if not line:
                raise JournalProjectionError(f"blank_record:{line_no}")
            total_records += 1
            try:
                record = json.loads(line, parse_constant=lambda _: (_ for _ in ()).throw(ValueError("non_finite_number")))
            except (json.JSONDecodeError, ValueError) as exc:
                raise JournalProjectionError(f"invalid_json:{line_no}") from exc
            if not isinstance(record, dict):
                raise JournalProjectionError(f"invalid_record_shape:{line_no}")
            digest = record.get("digest")
            event_id = record.get("event_id")
            if not isinstance(digest, str) or len(digest) != 64:
                raise JournalProjectionError(f"missing_digest:{line_no}")
            unsigned = dict(record)
            unsigned.pop("digest", None)
            if observation_digest(unsigned) != digest:
                raise JournalProjectionError(f"digest_mismatch:{line_no}")
            if not isinstance(event_id, str) or not event_id:
                raise JournalProjectionError(f"missing_event_id:{line_no}")
            if event_id in seen:
                if seen[event_id] != digest:
                    raise JournalProjectionError(f"conflicting_duplicate_event:{line_no}")
                raise JournalProjectionError(f"duplicate_event:{line_no}")
            seen[event_id] = digest
            if record.get("artifact_type") != "FORWARD_OBSERVATION" or record.get("artifact_version") != "1.0":
                raise JournalProjectionError(f"unsupported_artifact:{line_no}")
            if record.get("source_period") != "forward" or record.get("population") != "forward":
                raise JournalProjectionError(f"non_forward_record:{line_no}")
            if record.get("outcome") is not None or record.get("closed_at") is not None:
                raise JournalProjectionError(f"outcome_leakage_in_decision_journal:{line_no}")
            if record.get("decision") not in _ALLOWED_DECISIONS:
                raise JournalProjectionError(f"invalid_decision:{line_no}")
            observed_at = record.get("observed_at")
            if not isinstance(observed_at, str):
                raise JournalProjectionError(f"invalid_timestamp:{line_no}")
            try:
                parsed = datetime.fromisoformat(observed_at.replace("Z", "+00:00"))
            except ValueError as exc:
                raise JournalProjectionError(f"invalid_timestamp:{line_no}") from exc
            if parsed.tzinfo is None or parsed.utcoffset() is None:
                raise JournalProjectionError(f"naive_timestamp:{line_no}")
            if (parsed - current).total_seconds() > 5:
                raise JournalProjectionError(f"future_timestamp:{line_no}")
            reasons = record.get("reason_codes", [])
            if not isinstance(reasons, list) or any(not isinstance(reason, str) for reason in reasons):
                raise JournalProjectionError(f"invalid_reason_codes:{line_no}")
            events.append({
                "event_id": event_id,
                "observed_at": parsed.astimezone(timezone.utc).isoformat(),
                "symbol": record.get("symbol", "UNKNOWN"),
                "timeframe": record.get("timeframe", "UNKNOWN"),
                "decision": record["decision"],
                "status": record.get("status", "UNKNOWN"),
                "market_regime": record.get("market_regime", "UNKNOWN"),
                "decision_gate": record.get("decision_gate", "UNKNOWN"),
                "rejected_at": record.get("rejected_at") or "—",
                "reason_codes": reasons,
                "source": record.get("source", "UNKNOWN"),
                "product": record.get("product", "UNKNOWN"),
                "policy_version": record.get("policy_version", "UNKNOWN"),
                "response_sha256": record.get("response_sha256"),
                "htf_response_sha256": record.get("htf_response_sha256"),
                "event_sha256": digest,
                "execution": "OFF",
                "realized_outcome": "NOT_LINKED",
            })
            if len(events) > MAX_ROWS * 2:
                events.sort(key=lambda item: (item["observed_at"], item["event_id"]), reverse=True)
                del events[MAX_ROWS:]
    except JournalProjectionError:
        raise
    except OSError as exc:
        raise JournalProjectionError("journal_unavailable") from exc

    events.sort(key=lambda item: (item["observed_at"], item["event_id"]), reverse=True)
    return {
        "schema": "hes.trade_journal_view.v1",
        "status": "VERIFIED",
        "count": total_records,
        "events": events[:limit],
        "truncated": total_records > limit,
        "execution_enabled": False,
        "outcomes_inferred": False,
    }


def configured_decision_journal(*, limit: int = 50) -> dict[str, Any]:
    path = os.environ.get("HES_FORWARD_LEARNING_DECISION_JOURNAL", "").strip()
    if not path:
        return {
            "schema": "hes.trade_journal_view.v1",
            "status": "NOT_CONFIGURED",
            "count": 0,
            "events": [],
            "execution_enabled": False,
            "outcomes_inferred": False,
        }
    return read_decision_journal(path, limit=limit)
