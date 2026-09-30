"""Sample-level continuity evidence for completion-based collector handoff.

This harness is deliberately independent of the live collector. It validates the
boundary contract that a future production handoff artifact must satisfy:
last persisted event -> dispatch -> successor startup -> first event.
"""

from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(frozen=True)
class Event:
    sequence: int
    timestamp: datetime


@dataclass(frozen=True)
class HandoffEvidence:
    run_id: str
    predecessor_last: Event
    successor_first: Event
    dispatch_at: datetime
    successor_start_at: datetime


def _utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def measure_gap(evidence: HandoffEvidence) -> float:
    """Return wall-clock gap in seconds between predecessor and successor events."""
    return (evidence.successor_first.timestamp - evidence.predecessor_last.timestamp).total_seconds()


def validate_handoff(evidence: HandoffEvidence) -> list[str]:
    """Return explicit invariant violations; an empty list means PASS."""
    errors: list[str] = []
    if evidence.successor_first.sequence <= evidence.predecessor_last.sequence:
        errors.append("successor sequence must be strictly greater than predecessor sequence")
    if evidence.dispatch_at < evidence.predecessor_last.timestamp:
        errors.append("dispatch cannot precede predecessor last-event timestamp")
    if evidence.successor_start_at < evidence.dispatch_at:
        errors.append("successor startup cannot precede dispatch")
    if evidence.successor_first.timestamp < evidence.successor_start_at:
        errors.append("successor first event cannot precede successor startup")
    if measure_gap(evidence) < 0:
        errors.append("negative event-time handoff gap")
    return errors


def test_sample_level_n_to_n_plus_1_handoff_has_measurable_boundary():
    evidence = HandoffEvidence(
        run_id="N->N+1",
        predecessor_last=Event(1000, _utc("2026-09-30T00:00:00.000Z")),
        dispatch_at=_utc("2026-09-30T00:00:00.400Z"),
        successor_start_at=_utc("2026-09-30T00:00:01.100Z"),
        successor_first=Event(1001, _utc("2026-09-30T00:00:01.700Z")),
    )

    assert validate_handoff(evidence) == []
    assert measure_gap(evidence) == 1.7


def test_sample_level_sequence_regression_is_fail_closed():
    evidence = HandoffEvidence(
        run_id="N->N+1-regression",
        predecessor_last=Event(1000, _utc("2026-09-30T00:00:00Z")),
        dispatch_at=_utc("2026-09-30T00:00:00.1Z"),
        successor_start_at=_utc("2026-09-30T00:00:00.2Z"),
        successor_first=Event(999, _utc("2026-09-30T00:00:00.3Z")),
    )

    errors = validate_handoff(evidence)
    assert "successor sequence must be strictly greater than predecessor sequence" in errors


def test_sample_level_negative_time_boundary_is_fail_closed():
    evidence = HandoffEvidence(
        run_id="N->N+1-negative-time",
        predecessor_last=Event(1000, _utc("2026-09-30T00:00:02Z")),
        dispatch_at=_utc("2026-09-30T00:00:02.1Z"),
        successor_start_at=_utc("2026-09-30T00:00:02.2Z"),
        successor_first=Event(1001, _utc("2026-09-30T00:00:01.9Z")),
    )

    errors = validate_handoff(evidence)
    assert "successor first event cannot precede successor startup" in errors
    assert "negative event-time handoff gap" in errors
