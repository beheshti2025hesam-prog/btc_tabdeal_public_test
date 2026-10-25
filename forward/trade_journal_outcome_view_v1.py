"""Read-only join of the canonical decision log and existing immutable outcomes.

Validation and event linkage are delegated to the existing forward learning reader;
this module does not create an outcome schema or infer performance.
"""
from __future__ import annotations

from datetime import datetime
import os
from pathlib import Path
from typing import Any

from .learning_loop_v1 import build_report_from_forward_evidence
from .trade_journal_view_v1 import read_decision_journal, JournalProjectionError

MAX_ROWS = 100


class OutcomeProjectionError(ValueError):
    """The existing decision/outcome evidence cannot safely be projected."""


def _event_from_validated_row(row: dict[str, Any]) -> dict[str, Any]:
    outcome = row.get("outcome")
    return {
        "event_id": row.get("event_id"),
        "observed_at": row.get("observed_at"),
        "symbol": row.get("symbol", "UNKNOWN"),
        "timeframe": row.get("timeframe", "UNKNOWN"),
        "decision": row.get("decision", "UNKNOWN"),
        "decision_gate": row.get("decision_gate", "UNKNOWN"),
        "rejected_at": row.get("rejected_at") or "—",
        "reason_codes": row.get("reason_codes", []),
        "outcome": outcome if isinstance(outcome, str) else "NOT_LINKED",
        "closed_at": row.get("closed_at") if isinstance(row.get("closed_at"), str) else "NOT_LINKED",
        "realized_rr": row.get("realized_rr") if row.get("realized_rr") is not None else "UNKNOWN",
        "outcome_artifact_sha256": row.get("outcome_artifact_sha256"),
        "decision_event_sha256": row.get("event_sha256"),
        "fees": "UNKNOWN",
        "funding": "UNKNOWN",
        "realized_pnl": "UNKNOWN",
        "pnl_evidence": "NOT_LINKED",
    }


def read_outcome_projection(
    decision_journal_path: str | Path,
    outcome_dir: str | Path | None,
    *,
    limit: int = 50,
    now: datetime | None = None,
) -> dict[str, Any]:
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= MAX_ROWS:
        raise OutcomeProjectionError("invalid_limit")
    journal = Path(decision_journal_path)
    if outcome_dir is None:
        try:
            base = read_decision_journal(journal, limit=limit, now=now)
        except JournalProjectionError as exc:
            raise OutcomeProjectionError(str(exc)) from exc
        events = []
        for row in base["events"]:
            projected = _event_from_validated_row(row)
            events.append(projected)
        return {
            "schema": "hes.trade_journal_outcomes_view.v1",
            "status": "OUTCOMES_NOT_CONFIGURED",
            "count": base["count"],
            "events": events,
            "truncated": base.get("truncated", False),
            "execution_enabled": False,
            "outcomes_inferred": False,
        }

    outcomes = Path(outcome_dir)
    if outcomes.is_symlink() or not outcomes.is_dir():
        raise OutcomeProjectionError("outcome_directory_missing_or_unsafe")
    try:
        run = build_report_from_forward_evidence(journal, outcomes, now=now)
    except (OSError, ValueError) as exc:
        raise OutcomeProjectionError(str(exc)) from exc
    events = [_event_from_validated_row(row) for row in run.rows]
    events.sort(key=lambda row: (row.get("observed_at") or "", row.get("event_id") or ""), reverse=True)
    return {
        "schema": "hes.trade_journal_outcomes_view.v1",
        "status": "VERIFIED",
        "count": len(events),
        "events": events[:limit],
        "truncated": len(events) > limit,
        "outcome_artifact_count": run.evidence_manifest["outcome_artifact_count"],
        "outcome_manifest_sha256": run.evidence_manifest["outcome_manifest_sha256"],
        "decision_journal_sha256": run.evidence_manifest["decision_journal_sha256"],
        "execution_enabled": False,
        "outcomes_inferred": False,
    }


def configured_outcome_projection(*, limit: int = 50) -> dict[str, Any]:
    journal = os.environ.get("HES_FORWARD_LEARNING_DECISION_JOURNAL", "").strip()
    if not journal:
        return {
            "schema": "hes.trade_journal_outcomes_view.v1",
            "status": "NOT_CONFIGURED",
            "count": 0,
            "events": [],
            "execution_enabled": False,
            "outcomes_inferred": False,
        }
    outcome_dir = os.environ.get("HES_FORWARD_OUTCOMES_DIR", "").strip() or None
    return read_outcome_projection(journal, outcome_dir, limit=limit)
