import pytest
from forward.decision_gate_firewall_v1 import DecisionGateFirewallV1

BASE=dict(data_live=True,structure_safe=True,sequence_safe=True,clock_safe=True,
          health_safe=True,recovery_safe=True)
@pytest.mark.parametrize("field",[
"data_live","structure_safe","sequence_safe","clock_safe","health_safe","recovery_safe"])
def test_any_failed_safety_gate_forces_no_trade(field):
    args=BASE.copy(); args[field]=False
    r=DecisionGateFirewallV1().evaluate(**args)
    assert r.allowed is False
    assert r.decision=="NO_TRADE"

@pytest.mark.parametrize("field",[
"execution_enabled","historical_inputs_allowed","future_outcomes_allowed"])
def test_forbidden_runtime_state_forces_no_trade(field):
    args=BASE.copy(); args[field]=True
    r=DecisionGateFirewallV1().evaluate(**args)
    assert r.allowed is False
    assert r.decision=="NO_TRADE"

def test_safe_observation_still_cannot_execute():
    r=DecisionGateFirewallV1().evaluate(**BASE)
    assert r.allowed is True
    assert r.decision=="NO_TRADE"
    assert r.reason=="OBSERVATION_ONLY_NO_EXECUTION"
