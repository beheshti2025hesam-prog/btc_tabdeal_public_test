from types import SimpleNamespace
import pytest
from forward.indicator_strategy_family_v1 import evaluate_indicator_family, geometry, IndicatorCandidate

def snap(tf, regime, values):
    return SimpleNamespace(timeframe=tf, data_status="CLOSED_BARS_ONLY", candle_count=240,
        as_of=1700000000, regime=SimpleNamespace(label=regime),
        indicators={k:SimpleNamespace(value=v) for k,v in values.items()})

def test_trend_confirmation_requires_all_timeframes_and_conjunctive_evidence():
    vals={"atr_14":10,"ema_20":110,"ema_50":105,"ema_200":100,"adx_14":25,
          "plus_di_14":30,"minus_di_14":10,"rsi_14":60,"macd_histogram":2,"supertrend_direction":1,
          "donchian_upper_prior":120,"donchian_lower_prior":90,"roc_10_pct":1,
          "bollinger_percent_b":.5}
    c=evaluate_indicator_family(snap("15m","BULLISH",vals),snap("1h","BULLISH",vals),snap("4h","BULLISH",vals),close=115)
    assert [x.variant_id for x in c] == ["trend_confirmation"]

def test_no_signal_when_htf_disagrees_or_regime_transition():
    vals={"atr_14":10,"ema_20":110,"ema_50":105,"ema_200":100,"adx_14":25,
          "plus_di_14":30,"minus_di_14":10,"rsi_14":60,"macd_histogram":2,"supertrend_direction":1,
          "donchian_upper_prior":120,"donchian_lower_prior":90,"roc_10_pct":1}
    assert evaluate_indicator_family(snap("15m","BULLISH",vals),snap("1h","BEARISH",vals),snap("4h","BULLISH",vals),close=115)==[]
    assert evaluate_indicator_family(snap("15m","TRANSITION",vals),snap("1h","BULLISH",vals),snap("4h","BULLISH",vals),close=115)==[]

def test_range_mean_reversion_requires_range_and_extreme_confluence():
    vals={"atr_14":10,"bollinger_percent_b":.02,"rsi_14":25}
    c=evaluate_indicator_family(snap("15m","RANGE",vals),snap("1h","RANGE",vals),snap("4h","RANGE",vals),close=100)
    assert len(c)==1 and c[0].variant_id=="range_mean_reversion" and c[0].direction=="LONG"

def test_geometry_enforces_direction_and_three_r():
    c=IndicatorCandidate("indicator_strategy","v1","x","LONG","BULLISH",1,15,45,(),{})
    g=geometry(c,100)
    assert g and g["rr"]==pytest.approx(3.0) and g["stop_loss"]==85 and g["take_profit"]==145
    assert geometry(c,10) is None

def test_short_geometry_and_safety_are_research_only():
    c=IndicatorCandidate("indicator_strategy","v1","x","SHORT","BEARISH",1,15,45,(),{})
    g=geometry(c,100)
    assert g and g["stop_loss"]==115 and g["take_profit"]==55
    assert c.execution_enabled is False and c.orders_placed is False


def test_range_mean_reversion_fails_closed_on_unknown_or_transition_higher_timeframe():
    vals={"atr_14":10,"bollinger_percent_b":.02,"rsi_14":25}
    assert evaluate_indicator_family(
        snap("15m","RANGE",vals),snap("1h","UNKNOWN",vals),snap("4h","RANGE",vals),close=100
    ) == []
    assert evaluate_indicator_family(
        snap("15m","RANGE",vals),snap("1h","RANGE",vals),snap("4h","TRANSITION",vals),close=100
    ) == []
