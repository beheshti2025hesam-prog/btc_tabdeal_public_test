"""Fail-closed lineage contract for session -> execution -> Probe -> exit evidence.

This is a pure validator for explicit correlation links. It does not establish
exchange sequence semantics, source authenticity, registry trust, or permission
to execute trades.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from typing import Any, Iterable

SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
EXPECTED_TYPES = (
    "SESSION_STARTED",
    "EXECUTION_STARTED",
    "PROBE_RECORDED",
    "EXIT_RECORDED",
)


class EvidenceLineageError(ValueError):
    """Lineage evidence is malformed, ambiguous, or inconsistent."""


def canonical_event_sha256(event: dict[str, Any]) -> str:
    """Hash canonical event bytes excluding the self-referential digest field."""
    body = {key: value for key, value in event.items() if key != "event_sha256"}
    try:
        raw = json.dumps(
            body, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise EvidenceLineageError("EVENT_CANONICALIZATION_FAILED") from exc
    return hashlib.sha256(raw).hexdigest()


def _timestamp(value: Any) -> datetime:
    if not isinstance(value, str):
        raise EvidenceLineageError("TIMESTAMP_INVALID")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise EvidenceLineageError("TIMESTAMP_INVALID") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise EvidenceLineageError("TIMESTAMP_TIMEZONE_REQUIRED")
    return parsed


def verify_lineage(events: Iterable[dict[str, Any]]) -> dict[str, str]:
    """Verify exactly one ordered, hash-valid, explicitly linked four-event chain.

    Required fields on every event: event_id, event_type, session_id,
    execution_id, probe_id, parent_event_id, at_utc, event_sha256.
    A field not applicable to an earlier lifecycle stage must be null.
    The exit record additionally requires exit_event_id == event_id.
    """
    records = list(events)
    if len(records) != len(EXPECTED_TYPES):
        raise EvidenceLineageError("LINEAGE_EVENT_COUNT_INVALID")
    if any(not isinstance(record, dict) for record in records):
        raise EvidenceLineageError("EVENT_SCHEMA_INVALID")

    required = {
        "event_id", "event_type", "session_id", "execution_id", "probe_id",
        "parent_event_id", "at_utc", "event_sha256",
    }
    if any(set(record) != required | ({"exit_event_id"} if record.get("event_type") == "EXIT_RECORDED" else set())
           for record in records):
        raise EvidenceLineageError("EVENT_SCHEMA_INVALID")

    ids: list[str] = []
    previous_time: datetime | None = None
    for index, (record, expected_type) in enumerate(zip(records, EXPECTED_TYPES)):
        if record.get("event_type") != expected_type:
            raise EvidenceLineageError("EVENT_ORDER_INVALID")
        event_id = record.get("event_id")
        if not isinstance(event_id, str) or not event_id.strip():
            raise EvidenceLineageError("EVENT_ID_INVALID")
        ids.append(event_id)
        if not isinstance(record.get("session_id"), str) or not record["session_id"].strip():
            raise EvidenceLineageError("SESSION_ID_INVALID")
        for field in ("execution_id", "probe_id"):
            value = record.get(field)
            should_exist = index >= (1 if field == "execution_id" else 2)
            if should_exist and (not isinstance(value, str) or not value.strip()):
                raise EvidenceLineageError(f"{field.upper()}_INVALID")
            if not should_exist and value is not None:
                raise EvidenceLineageError(f"{field.upper()}_SCOPE_INVALID")
        if not isinstance(record.get("event_sha256"), str) or not SHA256_RE.fullmatch(record["event_sha256"]):
            raise EvidenceLineageError("EVENT_DIGEST_INVALID")
        if canonical_event_sha256(record) != record["event_sha256"]:
            raise EvidenceLineageError("EVENT_DIGEST_MISMATCH")
        at = _timestamp(record.get("at_utc"))
        if previous_time is not None and at < previous_time:
            raise EvidenceLineageError("EVENT_TIME_REGRESSION")
        previous_time = at

    if len(set(ids)) != len(ids):
        raise EvidenceLineageError("EVENT_ID_DUPLICATE")

    session, execution, probe, exit_event = records
    session_id = session["session_id"]
    execution_id = execution["execution_id"]
    probe_id = probe["probe_id"]

    if any(record["session_id"] != session_id for record in records):
        raise EvidenceLineageError("SESSION_LINEAGE_MISMATCH")
    if session["parent_event_id"] is not None:
        raise EvidenceLineageError("SESSION_PARENT_INVALID")
    if execution["parent_event_id"] != session["event_id"]:
        raise EvidenceLineageError("EXECUTION_PARENT_MISMATCH")
    if execution["session_id"] != session_id:
        raise EvidenceLineageError("EXECUTION_SESSION_MISMATCH")
    if probe["execution_id"] != execution_id or probe["parent_event_id"] != execution["event_id"]:
        raise EvidenceLineageError("PROBE_PARENT_MISMATCH")
    if exit_event["execution_id"] != execution_id or exit_event["probe_id"] != probe_id:
        raise EvidenceLineageError("EXIT_LINEAGE_MISMATCH")
    if exit_event["parent_event_id"] != probe["event_id"]:
        raise EvidenceLineageError("EXIT_PARENT_MISMATCH")
    if exit_event.get("exit_event_id") != exit_event["event_id"]:
        raise EvidenceLineageError("EXIT_EVENT_ID_MISMATCH")

    return {
        "session_id": session_id,
        "execution_id": execution_id,
        "probe_id": probe_id,
        "exit_event_id": exit_event["event_id"],
    }
