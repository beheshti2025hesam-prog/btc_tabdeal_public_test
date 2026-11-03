import pytest

from forward.integration_gate_v1 import ForwardIntegrationGateV1


BASE_SAFE = {
    "data_live": True,
    "structure_safe": True,
    "sequence_safe": True,
    "clock_safe": True,
    "health_safe": True,
    "recovery_safe": True,
}


def test_missing_safety_inputs_fail_closed_by_default():
    result = ForwardIntegrationGateV1().evaluate()
    assert result.safe is False
    assert result.decision == "NO_TRADE"
    assert result.reason == "DATA_NOT_LIVE"


@pytest.mark.parametrize("field", [
    "data_live", "structure_safe", "sequence_safe", "clock_safe", "health_safe", "recovery_safe",
])
def test_any_safety_break_cannot_bypass_final_gate(field):
    args = BASE_SAFE.copy()
    args[field] = False
    result = ForwardIntegrationGateV1().evaluate(**args)
    assert result.safe is False and result.decision == "NO_TRADE"


@pytest.mark.parametrize("field", [
    "execution_enabled", "historical_inputs_allowed", "future_outcomes_allowed",
])
def test_any_forbidden_runtime_state_cannot_bypass_final_gate(field):
    args = BASE_SAFE.copy()
    args[field] = True
    result = ForwardIntegrationGateV1().evaluate(**args)
    assert result.safe is False and result.decision == "NO_TRADE"


@pytest.mark.parametrize("field", [
    "data_live", "structure_safe", "sequence_safe", "clock_safe", "health_safe", "recovery_safe",
])
@pytest.mark.parametrize("value", [1, "true", None])
def test_truthy_or_missing_non_boolean_safety_inputs_fail_closed(field, value):
    args = BASE_SAFE.copy()
    args[field] = value
    result = ForwardIntegrationGateV1().evaluate(**args)
    assert result.safe is False and result.decision == "NO_TRADE"


@pytest.mark.parametrize("field", [
    "execution_enabled", "historical_inputs_allowed", "future_outcomes_allowed",
])
@pytest.mark.parametrize("value", [0, "false", None])
def test_non_boolean_forbidden_flags_fail_closed(field, value):
    args = BASE_SAFE.copy()
    args[field] = value
    result = ForwardIntegrationGateV1().evaluate(**args)
    assert result.safe is False and result.decision == "NO_TRADE"


def test_all_explicit_safe_inputs_still_observation_only():
    result = ForwardIntegrationGateV1().evaluate(**BASE_SAFE)
    assert result.safe is True
    assert result.decision == "NO_TRADE"
    assert result.reason == "OBSERVATION_ONLY_NO_EXECUTION"


def test_multiple_failures_remain_fail_closed():
    result = ForwardIntegrationGateV1().evaluate(data_live=False, sequence_safe=False, clock_safe=False)
    assert result.safe is False and result.decision == "NO_TRADE"
