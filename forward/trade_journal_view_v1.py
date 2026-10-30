"""Read-only projection of the canonical mixed HES trade journal.

Paper candidates/outcomes and Signal Agent decisions share one append-only file.
Only LONG/SHORT/NO_TRADE decision records are projected here; realized outcomes
are never inferred or written back into a decision.
"""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
from typing import Any

MAX_LINE_BYTES = 1024 * 1024
MAX_ROWS = 100
_ALLOWED_DECISIONS = {"LONG", "SHORT", "NO_TRADE"}


class JournalProjectionError(ValueError):
    """The canonical journal cannot safely be projected to the UI."""


def read_decision_journal(path: str | Path, *, limit: int = 50, now: datetime | None = None) -> dict[str, Any]:
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= MAX_ROWS:
        raise JournalProjectionError("invalid_limit")
    file_path = Path(path)
    try:
        if file_path.is_symlink() or not file_path.is_file():
            raise JournalProjectionError("journal_not_a_regular_file")
        size = file_path.stat().st_size
        if size == 0:
            return {"schema": "hes.trade_journal_view.v1", "status": "EMPTY", "count": 0, "decision_count": 0, "events": []}
        with file_path.open("rb") as handle:
            handle.seek(-1, 2)
            if handle.read(1) != b"\\n":
                raise JournalProjectionError("partial_trailing_record")
    except JournalProjectionError:
        raise
    except OSError as exc:
        raise JournalProjectionError("journal_unavailable") from exc

    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None or current.utcoffset() is None:
        raise JournalProjectionError("verifier_clock_not_timezone_aware")
    events: list[dict[str, Any]] = []
    seen: set[str] = set()
    total_records = 0
    decision_total = 0
    try:
        with file_path.open("rb") as handle:
            for line_no, raw_line in enumerate(handle, start=1):
                if len(raw_line) > MAX_LINE_BYTES:
                    raise JournalProjectionError(f"record_size_limit_exceeded:{line_no}")
                if not raw_line.endswith(b"\\n"):
                    raise JournalProjectionError("partial_trailing_record")
                try:
                    record = json.loads(raw_line.decode("utf-8", errors="strict"))
                except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                    raise JournalProjectionError(f"invalid_json:{line_no}") from exc
                if not isinstance(record, dict):
                    raise JournalProjectionError(f"invalid_record_shape:{line_no}")
                total_records += 1
                event_id = record.get("event_id")
                if not isinstance(event_id, str) or not event_id:
                    raise JournalProjectionError(f"missing_event_id:{line_no}")
                if event_id in seen:
                    raise JournalProjectionError(f"duplicate_event:{line_no}")
                seen.add(event_id)
                if record.get("decision") not in _ALLOWED_DECISIONS:
                    continue
                decision_total += 1
                if record.get("outcome") is not None or record.get("closed_at") is not None:
                    raise JournalProjectionError(f"outcome_leakage_in_decision_journal:{line_no}")
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
                if not reasons and record.get("no_trade_reason"):
                    reasons = str(record["no_trade_reason"]).split("|")
                if not isinstance(reasons, list) or any(not isinstance(reason, str) for reason in reasons):
                    raise JournalProjectionError(f"invalid_reason_codes:{line_no}")
                evidence_source = record.get("evidence_source")
                if not isinstance(evidence_source, (str, list, tuple)):
                    raise JournalProjectionError(f"missing_evidence_source:{line_no}")
                events.append({
                    "event_id": event_id,
                    "observed_at": parsed.astimezone(timezone.utc).isoformat(),
                    "symbol": record.get("symbol", "UNKNOWN"),
                    "timeframe": record.get("timeframe", "UNKNOWN"),
                    "decision": record["decision"],
                    "direction": record.get("direction", "NONE"),
                    "status": record.get("status", "RECORDED"),
                    "market_regime": record.get("market_regime", "UNKNOWN"),
                    "decision_gate": record.get("decision_gate", "UNKNOWN"),
                    "rejected_at": record.get("rejected_at") or "—",
                    "signal_state": record.get("signal_state", "UNKNOWN"),
                    "confirmation_state": record.get("confirmation_state", "UNKNOWN"),
                    "risk_state": record.get("risk_state", "UNKNOWN"),
                    "reason_codes": reasons,
                    "source": record.get("source", evidence_source),
                    "product": record.get("product", "UNKNOWN"),
                    "policy_version": record.get("policy_version", "UNKNOWN"),
                    "response_sha256": record.get("response_sha256"),
                    "htf_response_sha256": record.get("htf_response_sha256"),
                    "event_sha256": sha256(raw_line.rstrip(b"\\r\\n")).hexdigest(),
                    "execution": "OFF" if record.get("execution_enabled") is False and record.get("orders_placed") is False else "UNKNOWN",
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
        "decision_count": decision_total,
        "events": events[:limit],
        "truncated": total_records > limit,
        "execution_enabled": False,
        "outcomes_inferred": False,
    }


def configured_decision_journal(*, journal_path: str | Path | None = None, limit: int = 50) -> dict[str, Any]:
    configured = os.environ.get("HES_TRADE_JOURNAL_PATH", "").strip()
    path = Path(configured) if configured else Path(journal_path) if journal_path is not None else None
    if path is None:
        return {
            "schema": "hes.trade_journal_view.v1",
            "status": "NOT_CONFIGURED",
            "count": 0,
            "decision_count": 0,
            "events": [],
            "execution_enabled": False,
            "outcomes_inferred": False,
        }
    return read_decision_journal(path, limit=limit)
