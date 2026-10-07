from datetime import datetime, timezone

from forward.forward_run_controller_v1 import ForwardRunControllerV1


def test_run_rejects_pending_id_and_draft_policy():
    controller = ForwardRunControllerV1(
        policy={"status": "DRAFT_NOT_ACTIVE", "execution_enabled": False},
        ruleset={"status": "DRAFT_NOT_ACTIVE", "execution_enabled": False},
    )
    result = controller.start(
        run_id="FORWARD_RUN_PENDING",
        observed_at=datetime.now(timezone.utc),
        inputs=[],
    )
    assert result.status == "REJECTED"
    assert result.decision_count == 0


def test_ready_run_is_non_executing():
    controller = ForwardRunControllerV1(
        policy={
            "status": "ACTIVE",
            "historical_inputs_allowed": False,
            "historical_performance_tuning_allowed": False,
            "future_outcome_leakage_allowed": False,
            "execution_enabled": False,
        },
        ruleset={
            "status": "ACTIVE",
            "historical_inputs_allowed": False,
            "future_outcome_leakage_allowed": False,
            "execution_enabled": False,
        },
    )
    result = controller.start(
        run_id="FORWARD_RUN_TEST_001",
        observed_at=datetime.now(timezone.utc),
        inputs=[],
    )
    assert result.status == "READY"
    assert result.decision_count == 0
