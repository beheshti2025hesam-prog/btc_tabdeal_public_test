from datetime import datetime, timezone
from forward.confirmation_policy_v1 import ConfirmationPolicyV1
from forward.confirmation_engine_v1 import ConfirmationCheck
from forward.opportunity_detector_v1 import OpportunityCandidate
B=datetime(2026,10,7,tzinfo=timezone.utc)

def cand(state):
    return OpportunityCandidate(B,"BTC_USDT","15m",state,"UPTREND",("HH","HL"),("BOS",),("x",))

def checks(state="PASS"):
    return tuple(ConfirmationCheck(n,state,"forward:evidence:"+n,B) for n in ConfirmationPolicyV1.REQUIRED)

def test_long_confirmation():
    r=ConfirmationPolicyV1().evaluate(observed_at=B,candidate=cand("CANDIDATE_LONG"),checks=checks())
    assert r.state=="CONFIRMED_LONG" and r.passed_count==3

def test_short_confirmation():
    c=OpportunityCandidate(B,"BTC_USDT","15m","CANDIDATE_SHORT","DOWNTREND",("LL","LH"),("BOS",),("x",))
    r=ConfirmationPolicyV1().evaluate(observed_at=B,candidate=c,checks=checks())
    assert r.state=="CONFIRMED_SHORT"

def test_unknown_fails_closed():
    r=ConfirmationPolicyV1().evaluate(observed_at=B,candidate=cand("CANDIDATE_LONG"),checks=checks("UNKNOWN"))
    assert r.state=="UNCONFIRMED"

def test_missing_evidence_fails_closed():
    r=ConfirmationPolicyV1().evaluate(observed_at=B,candidate=cand("CANDIDATE_LONG"),checks=checks()[:2])
    assert r.state=="UNCONFIRMED"
