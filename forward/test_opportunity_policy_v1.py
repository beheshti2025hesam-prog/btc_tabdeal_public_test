from datetime import datetime, timezone
from forward.opportunity_policy_v1 import OpportunityPolicyV1
B=datetime(2026,10,7,tzinfo=timezone.utc)

def test_uptrend_structure_event_candidate_long():
    r=OpportunityPolicyV1().evaluate(observed_at=B,symbol='BTC_USDT',timeframe='15m',regime='UPTREND',structure_events=('HH','HL','BOS'))
    assert r.state=='CANDIDATE_LONG'

def test_downtrend_structure_event_candidate_short():
    r=OpportunityPolicyV1().evaluate(observed_at=B,symbol='BTC_USDT',timeframe='15m',regime='DOWNTREND',structure_events=('LL','LH','BOS'))
    assert r.state=='CANDIDATE_SHORT'

def test_unknown_regime_fails_closed():
    r=OpportunityPolicyV1().evaluate(observed_at=B,symbol='BTC_USDT',timeframe='15m',regime='UNKNOWN',structure_events=('BOS',))
    assert r.state=='NO_CANDIDATE'
