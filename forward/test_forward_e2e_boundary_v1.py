"""End-to-end fail-closed smoke test for the forward path."""

from datetime import datetime, timezone

from forward.decision_engine_v1 import DecisionEngineV1
from forward.forward_pipeline_v1 import ForwardPipelineV1
from forward.forward_run_controller_v1 import ForwardRunControllerV1
from forward.runtime_bridge_v1 import ForwardRuntimeBridgeV1


def test_forward_path_rejects_unactivated_policy_before_decision():
    controller = ForwardRunControllerV1(
        policy={
            "status": "DRAFT_NOT_ACTIVE",
            "historical_inputs_allowed": False,
            "historical_performance_tuning_allowed": False,
            "future_outcome_leakage_allowed": False,
            "execution_enabled": False,
        },
        ruleset={"status": "DRAFT_NOT_ACTIVE", "execution_enabled": False},
    )

    # Minimal injected pipeline object; this test proves the controller gate
    # blocks the path before any decision-producing call is permitted.
    class ExplodingPipeline:
        def run_once(self, **kwargs):
            raise AssertionError("pipeline must not be reached")

    bridge = ForwardRuntimeBridgeV1(
        controller=controller,
        pipeline=ExplodingPipeline(),
    )

    result = bridge.process_input(
        run_id="FORWARD_RUN_E2E_REJECT_001",
        observed_at=datetime.now(timezone.utc),
        market_input=object(),
    )

    assert result.status == "REJECTED"
    assert result.decision_count == 0
