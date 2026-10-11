"""Typed source-health evidence validation; this does not authorize network access.

The record is an input contract for adapters/tests, not proof of source authenticity.
Callers must not use it to unlock the sequence-semantic gate without independent
transport binding and an immutable, hash-verified registry artifact.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal


@dataclass(frozen=True)
class SourceHealthEvidenceV1:
    schema: str
    venue: str
    product: str
    endpoint: str
    topic: str
    expected_symbol: str
    observed_symbol: str
    session_id: str
    connection_id: str
    connection_generation: int
    source_event_time: datetime
    received_at: datetime
    schema_valid: bool
    validation_outcome: Literal["PASS", "FAIL"]
    reason_code: str


@dataclass(frozen=True)
class SourceHealthResultV1:
    healthy: bool
    reason_code: str


def _aware_utc(value: datetime) -> bool:
    return isinstance(value, datetime) and value.tzinfo is not None and value.utcoffset() is not None


def evaluate_source_health(
    evidence: SourceHealthEvidenceV1 | None,
    *,
    now: datetime,
    expected_venue: str,
    expected_product: str,
    expected_endpoint: str,
    expected_topic: str,
    expected_symbol: str,
    expected_session_id: str,
    max_age_seconds: float,
    max_future_skew_seconds: float = 2.0,
) -> SourceHealthResultV1:
    """Compute transport-message health conservatively; never infer sequence semantics."""
    if evidence is None:
        return SourceHealthResultV1(False, "SOURCE_HEALTH_EVIDENCE_MISSING")
    if not isinstance(evidence, SourceHealthEvidenceV1):
        return SourceHealthResultV1(False, "SOURCE_HEALTH_EVIDENCE_TYPE_INVALID")
    if not _aware_utc(now) or not _aware_utc(evidence.source_event_time) or not _aware_utc(evidence.received_at):
        return SourceHealthResultV1(False, "TIMESTAMP_TIMEZONE_REQUIRED")
    if max_age_seconds < 0 or max_future_skew_seconds < 0:
        return SourceHealthResultV1(False, "FRESHNESS_POLICY_INVALID")
    if evidence.schema != "hes_source_health_evidence_v1":
        return SourceHealthResultV1(False, "EVIDENCE_SCHEMA_MISMATCH")
    if not all((evidence.venue, evidence.product, evidence.endpoint, evidence.topic,
                evidence.expected_symbol, evidence.observed_symbol, evidence.session_id,
                evidence.connection_id, evidence.reason_code)):
        return SourceHealthResultV1(False, "EVIDENCE_REQUIRED_FIELD_MISSING")
    if (evidence.venue, evidence.product, evidence.endpoint, evidence.topic) != (
        expected_venue, expected_product, expected_endpoint, expected_topic
    ):
        return SourceHealthResultV1(False, "SOURCE_SCOPE_MISMATCH")
    if evidence.expected_symbol != expected_symbol or evidence.observed_symbol != expected_symbol:
        return SourceHealthResultV1(False, "SOURCE_SYMBOL_MISMATCH")
    if evidence.session_id != expected_session_id or evidence.connection_generation < 1:
        return SourceHealthResultV1(False, "SOURCE_SESSION_MISMATCH")
    if not isinstance(evidence.schema_valid, bool) or evidence.schema_valid is not True:
        return SourceHealthResultV1(False, "SOURCE_SCHEMA_INVALID")
    if evidence.validation_outcome != "PASS":
        return SourceHealthResultV1(False, "SOURCE_VALIDATION_FAILED")
    if evidence.received_at > now:
        return SourceHealthResultV1(False, "RECEIVE_TIME_IN_FUTURE")
    age = (now - evidence.received_at).total_seconds()
    if age > max_age_seconds:
        return SourceHealthResultV1(False, "SOURCE_MESSAGE_STALE")
    source_future = (evidence.source_event_time - now).total_seconds()
    if source_future > max_future_skew_seconds:
        return SourceHealthResultV1(False, "SOURCE_EVENT_TIME_IN_FUTURE")
    if evidence.source_event_time > evidence.received_at:
        source_to_receive = (evidence.source_event_time - evidence.received_at).total_seconds()
        if source_to_receive > max_future_skew_seconds:
            return SourceHealthResultV1(False, "SOURCE_EVENT_AFTER_RECEIVE")
    return SourceHealthResultV1(True, "SOURCE_MESSAGE_FRESH_AND_VALID")
