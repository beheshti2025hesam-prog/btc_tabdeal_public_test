import pytest

from forward.decision_gate_firewall_v1 import DecisionGateFirewallV1


BASE = dict(
    data_live=True,
    structure_safe=True,
    sequence_safe=True,
    clock_safe=True,
    health_safe=True,
    recovery_safe=True,
)


@pytest.mark.parametrize("field", [
    "data_live", "structure_safe", "sequence_safe", "clock_safe", "health_safe", "recovery_safe",
])
def test_any_failed_safety_gate_forces_no_trade(field):
    args = BASE.copy()
    args[field] = False
    result = DecisionGateFirewallV1().evaluate(**args)
    assert result.allowed is False
    assert result.decision == "NO_TRADE"


@pytest.mark.parametrize("field", [
    "execution_enabled", "historical_inputs_allowed", "future_outcomes_allowed",
])
def test_forbidden_runtime_state_forces_no_trade(field):
    args = BASE.copy()
    args[field] = True
    result = DecisionGateFirewallV1().evaluate(**args)
    assert result.allowed is False
    assert result.decision == "NO_TRADE"


@pytest.mark.parametrize("field", [
    "data_live", "structure_safe", "sequence_safe", "clock_safe", "health_safe", "recovery_safe",
])
@pytest.mark.parametrize("value", [1, "true", None])
def test_non_boolean_safety_values_are_not_accepted(field, value):
    args = BASE.copy()
    args[field] = value
    result = DecisionGateFirewallV1().evaluate(**args)
    assert result.allowed is False
    assert result.decision == "NO_TRADE"


@pytest.mark.parametrize("field", [
    "execution_enabled", "historical_inputs_allowed", "future_outcomes_allowed",
])
@pytest.mark.parametrize("value", [0, "false", None])
def test_non_boolean_forbidden_flags_are_not_accepted(field, value):
    args = BASE.copy()
    args[field] = value
    result = DecisionGateFirewallV1().evaluate(**args)
    assert result.allowed is False
    assert result.decision == "NO_TRADE"


def test_safe_observation_still_cannot_execute():
    result = DecisionGateFirewallV1().evaluate(**BASE)
    assert result.allowed is True
    assert result.decision == "NO_TRADE"
    assert result.reason == "OBSERVATION_ONLY_NO_EXECUTION"
