import pytest
from forward.blackbox_regime_brain_v1 import classify_regime

@pytest.mark.parametrize("raw,expected", [
    (("UPTREND","UPTREND","UPTREND"), "BULLISH"),
    (("DOWNTREND","DOWNTREND","DOWNTREND"), "BEARISH"),
    (("RANGE","RANGE","RANGE"), "RANGE"),
])
def test_four_state_brain_keeps_three_market_regimes_first_class(raw, expected):
    got=classify_regime(regimes=raw,data_fresh=True,data_complete=True,confidence=.9)
    assert got.state == expected and got.actionable

@pytest.mark.parametrize("raw,reason", [
    (("RANGE","UPTREND","RANGE"),"MULTI_TIMEFRAME_REGIME_CONFLICT"),
    (("TRANSITION","RANGE","RANGE"),"TRANSITION_OR_UNKNOWN_REGIME"),
    (("UNKNOWN","UNKNOWN","UNKNOWN"),"TRANSITION_OR_UNKNOWN_REGIME"),
])
def test_ambiguous_or_mixed_regime_fails_closed(raw, reason):
    got=classify_regime(regimes=raw,data_fresh=True,data_complete=True,confidence=.99)
    assert got.state=="NO_TRADE" and not got.actionable and got.reason==reason

def test_stale_or_incomplete_data_is_no_trade_even_for_strong_range():
    for kwargs in ({"data_fresh":False,"data_complete":True},{"data_fresh":True,"data_complete":False}):
        got=classify_regime(regimes=("RANGE",)*3,confidence=.99,**kwargs)
        assert got.state=="NO_TRADE" and not got.actionable

def test_low_confidence_and_wrong_timeframe_count_are_no_trade():
    assert classify_regime(regimes=("RANGE",)*3,data_fresh=True,data_complete=True,confidence=.4).state=="NO_TRADE"
    assert classify_regime(regimes=("RANGE","RANGE"),data_fresh=True,data_complete=True,confidence=.99).state=="NO_TRADE"
