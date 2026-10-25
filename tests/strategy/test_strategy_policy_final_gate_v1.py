from forward.strategy_policy_v2 import PolicyDecision, POLICY_VERSION
from forward.strategy_policy_gate_v1 import enforce_final_gates, GATE_VERSION, REQUIRED_UNWIRED_GATES


def proposal(decision):
    return PolicyDecision(
        POLICY_VERSION, decision, decision if decision in ("LONG", "SHORT") else "NONE", 100,
        100.0 if decision in ("LONG", "SHORT") else None,
        98.0 if decision == "LONG" else 102.0 if decision == "SHORT" else None,
        106.0 if decision == "LONG" else 94.0 if decision == "SHORT" else None,
        3.0 if decision in ("LONG", "SHORT") else None,
        ("ALL_POLICY_GATES_PASSED",), {"policy": "PASS"},
    )


def test_long_proposal_cannot_bypass_unwired_structure_confirmation_risk():
    decision = enforce_final_gates(proposal("LONG"))
    assert decision.decision == "NO_TRADE" and decision.direction == "NONE"
    assert decision.reasons == REQUIRED_UNWIRED_GATES
    assert decision.proposal["decision"] == "LONG"
    assert decision.execution_enabled is False and decision.orders_placed is False


def test_short_proposal_cannot_bypass_unwired_structure_confirmation_risk():
    decision = enforce_final_gates(proposal("SHORT"))
    assert decision.decision == "NO_TRADE" and decision.direction == "NONE"
    assert decision.reasons == REQUIRED_UNWIRED_GATES
    assert decision.proposal["decision"] == "SHORT"
    assert decision.execution_enabled is False and decision.orders_placed is False


def test_no_trade_stays_no_trade():
    decision = enforce_final_gates(proposal("NO_TRADE"))
    assert decision.decision == "NO_TRADE"
    assert decision.execution_enabled is False and decision.orders_placed is False
    assert decision.gate_version == GATE_VERSION
