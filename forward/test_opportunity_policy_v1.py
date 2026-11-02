from datetime import datetime, timezone
from forward.opportunity_policy_v1 import OpportunityPolicyV1
B=datetime(2026,10,7,tzinfo=timezone.utc)

def test_uptrend_structure_event_candidate_long():
    r=OpportunityPolicyV1().evaluate(observed_at=B,symbol='BTC_USDT',timeframe='15m',regime='UPTREND',structure_labels=('HH','HL'),structure_events=('HH','HL','BOS'))
    assert r.state=='CANDIDATE_LONG'

def test_downtrend_structure_event_candidate_short():
    r=OpportunityPolicyV1().evaluate(observed_at=B,symbol='BTC_USDT',timeframe='15m',regime='DOWNTREND',structure_labels=('LL','LH'),structure_events=('LL','LH','BOS'))
    assert r.state=='CANDIDATE_SHORT'

def test_unknown_regime_fails_closed():
    r=OpportunityPolicyV1().evaluate(observed_at=B,symbol='BTC_USDT',timeframe='15m',regime='UNKNOWN',structure_events=('BOS',))
    assert r.state=='NO_CANDIDATE'


def test_opportunity_scope_is_configurable_without_copying_policy_logic():
    policy = OpportunityPolicyV1(allowed_scopes=(("ETHUSDT", "1h"),))
    result = policy.evaluate(
        observed_at=B, symbol="ETHUSDT", timeframe="1h", regime="UPTREND",
        structure_labels=("HH", "HL"), structure_events=("HL",),
    )
    assert result.state == "CANDIDATE_LONG"


def test_invalid_or_duplicate_allowed_scopes_are_rejected():
    import pytest

    with pytest.raises(ValueError):
        OpportunityPolicyV1(allowed_scopes=(("BTC_USDT", "15m"), ("BTC_USDT", "15m")))
    with pytest.raises(ValueError):
        OpportunityPolicyV1(allowed_scopes=(("", "15m"),))
