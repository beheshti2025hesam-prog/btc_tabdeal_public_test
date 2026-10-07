from forward.controlled_forward_observation_runner_v1 import (
    ControlledObservationRunnerResult,
)
from forward.runtime_health_gate_v1 import ForwardRuntimeHealthGateV1


def result(status, reason, records=0, snapshot_id=None, diagnostics=()):
    return ControlledObservationRunnerResult(
        run_id="OBS-TEST",
        status=status,
        records_received=records,
        journal_path="/tmp/journal.jsonl",
        reason=reason,
        snapshot_id=snapshot_id,
        diagnostics=diagnostics,
    )


def test_health_gate_maps_healthy_observation_without_reinterpreting_reason():
    evaluated = ForwardRuntimeHealthGateV1.evaluate(
        result("OBSERVED", "RECORDED", records=7, snapshot_id="SNAP-1")
    )
    assert evaluated.health == "HEALTHY"
    assert evaluated.source_status == "OBSERVED"
    assert evaluated.source_reason == "RECORDED"
    assert evaluated.records_received == 7
    assert evaluated.observation_safe is True


def test_health_gate_maps_waiting_without_mutating_runner_state():
    evaluated = ForwardRuntimeHealthGateV1.evaluate(
        result("WAITING", "NO_FRESH_RECORDS")
    )
    assert evaluated.health == "WAITING"
    assert evaluated.observation_safe is False


def test_health_gate_preserves_data_safety_block_as_blocked():
    evaluated = ForwardRuntimeHealthGateV1.evaluate(
        result(
            "BLOCKED",
            "SEQUENCE_UNSAFE",
            records=7,
            diagnostics=(
                {"sequence": 1, "status": "ACCEPTED", "reason": None},
                {"sequence": 3, "status": "ANOMALY", "reason": "SEQUENCE_GAP"},
            ),
        )
    )
    assert evaluated.health == "BLOCKED"
    assert evaluated.source_reason == "SEQUENCE_UNSAFE"
    assert evaluated.diagnostics_count == 2


def test_health_gate_distinguishes_transport_error():
    evaluated = ForwardRuntimeHealthGateV1.evaluate(
        result("BLOCKED", "TRANSPORT_ERROR:RuntimeError")
    )
    assert evaluated.health == "TRANSPORT_ERROR"


def test_health_gate_rejects_unknown_status():
    try:
        ForwardRuntimeHealthGateV1.evaluate(result("UNKNOWN", "x"))
    except ValueError as exc:
        assert "unknown runner status" in str(exc)
    else:
        raise AssertionError("unknown status must fail closed")
