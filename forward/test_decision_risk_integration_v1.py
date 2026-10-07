"""Integration boundary: Confirmation -> Risk Gate -> Final Decision."""
from datetime import datetime, timezone
from forward.decision_engine_v1 import DecisionEngineV1
from forward.risk_gate_v1 import RiskCheck
from forward.risk_policy_v1 import RiskPolicyV1

OBS=datetime(2026,10,7,tzinfo=timezone.utc)

def _confirmation(state):
    return type("Confirmation", (), {"state": state})()

def _candidate(state):
    return type("Candidate", (), {"state": state})()

def _checks(state="PASS"):
    return tuple(RiskCheck(n,state,"forward:risk:"+n,OBS) for n in RiskPolicyV1.REQUIRED)

def test_risk_veto_forces_no_trade():
    risk=RiskPolicyV1().evaluate(observed_at=OBS,confirmation=_confirmation("CONFIRMED_LONG"),checks=_checks("FAIL"))
    result=DecisionEngineV1().evaluate(observed_at=OBS,candidate=_candidate("CANDIDATE_LONG"),confirmation=_confirmation("CONFIRMED_LONG"),risk=risk)
    assert risk.state=="RISK_REJECTED"
    assert result.decision=="NO_TRADE"
    assert "RISK_NOT_APPROVED" in result.reason_codes

def test_long_requires_all_three_gates():
    risk=RiskPolicyV1().evaluate(observed_at=OBS,confirmation=_confirmation("CONFIRMED_LONG"),checks=_checks())
    result=DecisionEngineV1().evaluate(observed_at=OBS,candidate=_candidate("CANDIDATE_LONG"),confirmation=_confirmation("CONFIRMED_LONG"),risk=risk)
    assert risk.state=="RISK_APPROVED"
    assert result.decision=="LONG"

def test_short_requires_directional_alignment():
    risk=RiskPolicyV1().evaluate(observed_at=OBS,confirmation=_confirmation("CONFIRMED_SHORT"),checks=_checks())
    result=DecisionEngineV1().evaluate(observed_at=OBS,candidate=_candidate("CANDIDATE_SHORT"),confirmation=_confirmation("CONFIRMED_SHORT"),risk=risk)
    assert risk.state=="RISK_APPROVED"
    assert result.decision=="SHORT"
