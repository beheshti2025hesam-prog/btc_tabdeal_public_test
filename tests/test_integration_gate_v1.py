import pytest
from forward.integration_gate_v1 import ForwardIntegrationGateV1

BASE={}
@pytest.mark.parametrize("field",[
"data_live","structure_safe","sequence_safe","clock_safe","health_safe","recovery_safe",
])
def test_any_safety_break_cannot_bypass_final_gate(field):
    args={k:True for k in ["data_live","structure_safe","sequence_safe","clock_safe","health_safe","recovery_safe"]}
    args[field]=False
    r=ForwardIntegrationGateV1().evaluate(**args)
    assert r.safe is False and r.decision=="NO_TRADE"

@pytest.mark.parametrize("field",["execution_enabled","historical_inputs_allowed","future_outcomes_allowed"])
def test_any_forbidden_runtime_state_cannot_bypass_final_gate(field):
    args={k:True for k in ["data_live","structure_safe","sequence_safe","clock_safe","health_safe","recovery_safe"]}
    args[field]=True
    r=ForwardIntegrationGateV1().evaluate(**args)
    assert r.safe is False and r.decision=="NO_TRADE"

def test_all_safe_still_observation_only():
    r=ForwardIntegrationGateV1().evaluate()
    assert r.safe is True and r.decision=="NO_TRADE"

def test_multiple_failures_remain_fail_closed():
    r=ForwardIntegrationGateV1().evaluate(data_live=False,sequence_safe=False,clock_safe=False)
    assert r.safe is False and r.decision=="NO_TRADE"
