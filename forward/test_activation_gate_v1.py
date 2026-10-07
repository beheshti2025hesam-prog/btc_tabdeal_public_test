from forward.activation_gate_v1 import validate_activation


def test_draft_policy_cannot_activate():
    policy = {
        "status": "DRAFT_NOT_ACTIVE",
        "historical_inputs_allowed": False,
        "historical_performance_tuning_allowed": False,
        "future_outcome_leakage_allowed": False,
        "execution_enabled": False,
    }
    ruleset = {"status": "DRAFT_NOT_ACTIVE", "execution_enabled": False}
    result = validate_activation(policy, ruleset)
    assert result.active is False
    assert "POLICY_NOT_ACTIVE" in result.errors
    assert "RULESET_NOT_ACTIVE" in result.errors


def test_forbidden_execution_blocks_activation():
    policy = {
        "status": "ACTIVE",
        "historical_inputs_allowed": False,
        "historical_performance_tuning_allowed": False,
        "future_outcome_leakage_allowed": False,
        "execution_enabled": True,
    }
    ruleset = {
        "status": "ACTIVE",
        "historical_inputs_allowed": False,
        "future_outcome_leakage_allowed": False,
        "execution_enabled": False,
    }
    result = validate_activation(policy, ruleset)
    assert result.active is False
    assert "LIVE_EXECUTION_FORBIDDEN" in result.errors
