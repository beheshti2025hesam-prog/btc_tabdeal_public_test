"""Forward runtime validation helpers.

These checks are descriptive/safety-only and do not execute orders or tune
strategy parameters.
"""
from __future__ import annotations

from typing import Any, Mapping


def validate_decision_record(record: Mapping[str, Any]) -> tuple[str, ...]:
    errors: list[str] = []
    if record.get("decision") not in {"LONG", "SHORT", "NO_TRADE"}:
        errors.append("INVALID_DECISION")
    if not record.get("event_id"):
        errors.append("MISSING_EVENT_ID")
    if not record.get("observed_at"):
        errors.append("MISSING_OBSERVED_AT")
    if not record.get("evidence_source"):
        errors.append("MISSING_EVIDENCE_SOURCE")
    if record.get("outcome") not in {None}:
        errors.append("DECISION_CONTAINS_FUTURE_OUTCOME")
    if record.get("decision") == "NO_TRADE" and not record.get("no_trade_reason"):
        errors.append("NO_TRADE_REASON_REQUIRED")
    return tuple(errors)


def validate_outcome_artifact(
    artifact: Mapping[str, Any],
    *,
    decision_event_ids: set[str],
) -> tuple[str, ...]:
    errors: list[str] = []
    if artifact.get("event_id") not in decision_event_ids:
        errors.append("UNKNOWN_DECISION_EVENT_ID")
    if artifact.get("outcome") not in {"WIN", "LOSS", "BREAKEVEN", "CANCELLED"}:
        errors.append("INVALID_OUTCOME")
    if not artifact.get("closed_at"):
        errors.append("MISSING_CLOSED_AT")
    return tuple(errors)
