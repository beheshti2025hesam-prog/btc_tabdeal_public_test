"""Typed, fail-closed source-health evidence evaluation for observation heartbeats.

This module validates evidence; it does not connect to a venue or collect data.
A caller-provided boolean is deliberately not accepted as proof of source health.
"""
from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any, Mapping

SCHEMA = "hes_source_health_evidence_v1"
REQUIRED_FIELDS = {
    "schema", "venue", "product", "endpoint", "topic",
    "expected_symbol", "observed_symbol", "connection_id",
    "session_id", "session_generation", "source_event_at_utc",
    "received_at_utc", "freshness_bound_seconds",
    "schema_validated", "schema_validation_reason", "reason_code",
}
EXPECTED_VENUE = "tabdeal"
EXPECTED_PRODUCT = "futures"
EXPECTED_ENDPOINT = "wss://api1.tabdeal.org/special_margin/broadcast/"
EXPECTED_TOPIC = "trade"


def _parse_aware_utc(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(timezone.utc)


def evaluate_source_health(
    evidence: Mapping[str, Any],
    *,
    expected_run_id: str,
    expected_session_generation: int,
    expected_symbol: str,
    now_utc: datetime,
    max_receive_clock_skew_seconds: float = 5.0,
) -> dict[str, str]:
    """Return computed health and a stable reason; never trust claimed health."""
    def unhealthy(reason: str) -> dict[str, str]:
        return {"source_health": "UNHEALTHY", "reason_code": reason}

    if not isinstance(evidence, Mapping) or set(evidence.keys()) != REQUIRED_FIELDS:
        return unhealthy("SOURCE_HEALTH_EVIDENCE_SCHEMA_INVALID")
    if evidence.get("schema") != SCHEMA:
        return unhealthy("SOURCE_HEALTH_EVIDENCE_SCHEMA_INVALID")
    for field in ("venue", "product", "endpoint", "topic"):
        if not isinstance(evidence.get(field), str) or not evidence[field].strip():
            return unhealthy("SOURCE_HEALTH_SCOPE_INVALID")
    if (
        evidence["venue"] != EXPECTED_VENUE
        or evidence["product"] != EXPECTED_PRODUCT
        or evidence["endpoint"] != EXPECTED_ENDPOINT
        or evidence["topic"] != EXPECTED_TOPIC
    ):
        return unhealthy("SOURCE_HEALTH_SCOPE_MISMATCH")
    claimed_expected_symbol = evidence.get("expected_symbol")
    observed_symbol = evidence.get("observed_symbol")
    if not isinstance(expected_symbol, str) or not expected_symbol.strip():
        return unhealthy("SOURCE_HEALTH_EXPECTED_SYMBOL_INVALID")
    if not isinstance(claimed_expected_symbol, str) or not claimed_expected_symbol.strip():
        return unhealthy("SOURCE_HEALTH_EXPECTED_SYMBOL_INVALID")
    if claimed_expected_symbol != expected_symbol:
        return unhealthy("SOURCE_HEALTH_EXPECTED_SYMBOL_MISMATCH")
    if not isinstance(observed_symbol, str) or not observed_symbol.strip():
        return unhealthy("SOURCE_HEALTH_SYMBOL_INVALID")
    if observed_symbol != expected_symbol:
        return unhealthy("SOURCE_HEALTH_SYMBOL_MISMATCH")
    for field in ("connection_id", "session_id"):
        if not isinstance(evidence.get(field), str) or not evidence[field].strip():
            return unhealthy("SOURCE_HEALTH_SESSION_IDENTITY_INVALID")
    if evidence["session_id"] != expected_run_id:
        return unhealthy("SOURCE_HEALTH_SESSION_MISMATCH")
    generation = evidence.get("session_generation")
    if isinstance(generation, bool) or not isinstance(generation, int) or generation < 1:
        return unhealthy("SOURCE_HEALTH_SESSION_GENERATION_INVALID")
    if generation != expected_session_generation:
        return unhealthy("SOURCE_HEALTH_SESSION_GENERATION_MISMATCH")
    if type(evidence.get("schema_validated")) is not bool:
        return unhealthy("SOURCE_HEALTH_SCHEMA_VALIDATION_INVALID")
    validation_reason = evidence.get("schema_validation_reason")
    if not isinstance(validation_reason, str) or not validation_reason.strip() or len(validation_reason) > 120:
        return unhealthy("SOURCE_HEALTH_SCHEMA_VALIDATION_INVALID")
    if evidence["schema_validated"] is not True:
        return unhealthy("SOURCE_SCHEMA_VALIDATION_FAILED")
    if validation_reason != "SCHEMA_VALID":
        return unhealthy("SOURCE_HEALTH_SCHEMA_VALIDATION_CONTRADICTION")
    claimed_reason = evidence.get("reason_code")
    if not isinstance(claimed_reason, str) or not claimed_reason.strip() or len(claimed_reason) > 120:
        return unhealthy("SOURCE_HEALTH_REASON_INVALID")

    bound = evidence.get("freshness_bound_seconds")
    if isinstance(bound, bool) or not isinstance(bound, (int, float)):
        return unhealthy("SOURCE_HEALTH_FRESHNESS_BOUND_INVALID")
    try:
        bound_float = float(bound)
        skew_float = float(max_receive_clock_skew_seconds)
    except (OverflowError, TypeError, ValueError):
        return unhealthy("SOURCE_HEALTH_FRESHNESS_BOUND_INVALID")
    if not math.isfinite(bound_float) or bound_float <= 0:
        return unhealthy("SOURCE_HEALTH_FRESHNESS_BOUND_INVALID")
    if not math.isfinite(skew_float) or skew_float < 0:
        return unhealthy("SOURCE_HEALTH_CLOCK_SKEW_BOUND_INVALID")

    source_at = _parse_aware_utc(evidence.get("source_event_at_utc"))
    received_at = _parse_aware_utc(evidence.get("received_at_utc"))
    if source_at is None or received_at is None:
        return unhealthy("SOURCE_HEALTH_TIMESTAMP_INVALID")
    if now_utc.tzinfo is None or now_utc.utcoffset() is None:
        return unhealthy("SOURCE_HEALTH_REFERENCE_CLOCK_INVALID")
    now = now_utc.astimezone(timezone.utc)
    receive_skew = abs((now - received_at).total_seconds())
    if receive_skew > skew_float:
        return unhealthy("SOURCE_RECEIVE_TIMESTAMP_STALE_OR_FUTURE")
    if source_at > received_at:
        return unhealthy("SOURCE_EVENT_TIMESTAMP_IN_FUTURE")
    age = (received_at - source_at).total_seconds()
    if age < 0:
        return unhealthy("SOURCE_EVENT_TIMESTAMP_IN_FUTURE")
    if age > bound_float:
        return unhealthy("SOURCE_STALE")
    if claimed_reason != "SOURCE_HEALTHY":
        return unhealthy("SOURCE_HEALTH_REASON_CONTRADICTION")
    return {"source_health": "HEALTHY", "reason_code": "SOURCE_HEALTHY"}
