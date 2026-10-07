from datetime import datetime, timezone
from forward.risk_policy_v1 import RiskPolicyV1
from forward.risk_gate_v1 import RiskCheck
B=datetime(2026,10,7,tzinfo=timezone.utc)

def checks(state="PASS"):
    return tuple(RiskCheck(n,state,"forward:risk:"+n,B) for n in RiskPolicyV1.REQUIRED)

def test_approved_when_all_risk_checks_pass():
    r=RiskPolicyV1().evaluate(observed_at=B,confirmation=type("C",(),{"state":"CONFIRMED_LONG"})(),checks=checks())
    assert r.state=="RISK_APPROVED"

def test_unknown_rejected():
    r=RiskPolicyV1().evaluate(observed_at=B,confirmation=type("C",(),{"state":"CONFIRMED_LONG"})(),checks=checks("UNKNOWN"))
    assert r.state=="RISK_REJECTED"

def test_unconfirmed_rejected():
    r=RiskPolicyV1().evaluate(observed_at=B,confirmation=type("C",(),{"state":"UNCONFIRMED"})(),checks=checks())
    assert r.state=="RISK_REJECTED"
