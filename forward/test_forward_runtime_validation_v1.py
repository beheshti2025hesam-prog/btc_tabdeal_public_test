from forward.forward_runtime_validation_v1 import (
    validate_decision_record,
    validate_outcome_artifact,
)


def test_decision_cannot_carry_future_outcome():
    record = {
        "event_id": "evt-1",
        "observed_at": "2026-10-07T01:00:00+00:00",
        "decision": "LONG",
        "evidence_source": "forward",
        "outcome": "WIN",
    }
    assert "DECISION_CONTAINS_FUTURE_OUTCOME" in validate_decision_record(record)


def test_no_trade_requires_reason():
    record = {
        "event_id": "evt-2",
        "observed_at": "2026-10-07T01:00:00+00:00",
        "decision": "NO_TRADE",
        "evidence_source": "forward",
        "outcome": None,
    }
    assert "NO_TRADE_REASON_REQUIRED" in validate_decision_record(record)


def test_outcome_must_reference_decision():
    artifact = {
        "event_id": "missing",
        "outcome": "WIN",
        "closed_at": "2026-10-07T01:15:00+00:00",
    }
    assert validate_outcome_artifact(artifact, decision_event_ids=set()) == (
        "UNKNOWN_DECISION_EVENT_ID",
    )


def test_valid_outcome_passes():
    artifact = {
        "event_id": "evt-1",
        "outcome": "LOSS",
        "closed_at": "2026-10-07T01:15:00+00:00",
    }
    assert validate_outcome_artifact(artifact, decision_event_ids={"evt-1"}) == ()
