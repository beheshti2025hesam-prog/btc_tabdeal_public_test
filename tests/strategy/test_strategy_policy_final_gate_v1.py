from forward.strategy_policy_v2 import PolicyDecision, POLICY_VERSION
from forward.strategy_policy_gate_v1 import enforce_final_gates, GATE_VERSION, REQUIRED_UNWIRED_GATES

def proposal(decision):
    return PolicyDecision(POLICY_VERSION, decision, decision if decision in ('LONG','SHORT') else 'NONE', 100,
        100.0 if decision in ('LONG','SHORT') else None,
        98.0 if decision == 'LONG' else 102.0 if decision == 'SHORT' else None,
        106.0 if decision == 'LONG' else 94.0 if decision == 'SHORT' else None,
        3.0 if decision in ('LONG','SHORT') else None, ('ALL_POLICY_GATES_PASSED',), {'policy':'PASS'})

def test_long_proposal_cannot_bypass_unwired_structure_confirmation_risk():
    d=enforce_final_gates(proposal('LONG'))
    assert d.decision == 'NO_TRADE' and d.direction == 'NONE'
    assert d.reasons == REQUIRED_UNWIRED_GATES
    assert d.proposal['decision'] == 'LONG'
    assert d.execution_enabled is False and d.orders_placed is False

def test_short_proposal_cannot_bypass_unwired_structure_confirmation_risk():
    d=enforce_final_gates(proposal('SHORT'))
    assert d.decision == 'NO_TRADE' and d.direction == 'NONE'
    assert d.reasons == REQUIRED_UNWIRED_GATES
    assert d.execution_enabled is False and d.orders_placed is False

def test_no_trade_stays_no_trade():
    d=enforce_final_gates(proposal('NO_TRADE'))
    assert d.decision == 'NO_TRADE' and d.execution_enabled is False
    assert d.gate_version == GATE_VERSION
