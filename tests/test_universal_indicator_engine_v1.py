import math
import json
from pathlib import Path
import pytest

from forward.universal_indicator_engine_v1 import (
    DEFAULT_PERIODS, INDICATOR_REGISTRY, REGIME_POLICY, REGIME_INDICATOR_PROFILES,
    FAMILY_WEIGHTS, build_snapshot, calculate_indicators, dashboard_payload, normalize_bars,
)


def make_bars(mode="up", count=320, volume=True, quote=True):
    rows=[]
    previous=100.0
    for i in range(count):
        if mode=="up":
            close=100+i*.18+math.sin(i/4)*.08
        elif mode=="down":
            close=160-i*.18+math.sin(i/4)*.08
        elif mode=="range":
            close=100+math.sin(i/2)*1.2+math.sin(i/9)*.2
        else:
            close=100+math.sin(i/3)*.5+(i*.025 if i>count*.7 else 0)
        op=previous
        high=max(op,close)+.25
        low=min(op,close)-.25
        row={"timestamp":i*60,"open":op,"high":high,"low":low,"close":close,"closed":True}
        if volume: row["volume"]=100+i%9
        if quote and volume: row["quote_volume"]=(100+i%9)*((op+close)/2)
        rows.append(row);previous=close
    return rows


def snapshot(mode="up", **kwargs):
    qualified=kwargs.pop("volume_semantics_qualified",True)
    return build_snapshot(make_bars(mode, **kwargs),venue="gateio",market="spot",symbol="BTC_USDT",timeframe="1m",volume_semantics_qualified=qualified)


def test_registry_is_multi_market_and_volume_qualified():
    assert INDICATOR_REGISTRY["rsi"]["markets"]=="all"
    assert INDICATOR_REGISTRY["vwap"]["markets"]=="venue_volume_qualified"
    assert len(DEFAULT_PERIODS)>=25


def test_uptrend_classified_bullish():
    s=snapshot("up")
    assert s.regime.label=="BULLISH"
    assert s.indicators["adx_14"].value <= 100
    assert s.indicators["plus_di_14"].value > s.indicators["minus_di_14"].value
    assert s.regime_profile["regime"]=="BULLISH"
    assert "adx_14" in s.regime_profile["primary_indicators"]
    assert s.regime_profile["selection_is_trade_signal"] is False


def test_downtrend_classified_bearish():
    s=snapshot("down")
    assert s.regime.label=="BEARISH"
    assert s.indicators["minus_di_14"].value > s.indicators["plus_di_14"].value


def test_range_classified_range():
    s=snapshot("range")
    assert s.regime.label=="RANGE"
    assert s.indicators["efficiency_ratio_20"].value < .3
    assert "bollinger_percent_b" in s.regime_profile["primary_indicators"]


def test_insufficient_history_is_unknown():
    s=snapshot("up",count=80)
    assert s.regime.label=="UNKNOWN"
    assert s.regime.evidence_confidence is None


def test_open_candles_are_excluded():
    rows=make_bars("up")
    rows[-1]["closed"]=False
    b=normalize_bars(rows)
    assert len(b)==len(rows)-1
    assert b[-1].timestamp==rows[-2]["timestamp"]


def test_duplicate_or_out_of_order_timestamps_rejected():
    rows=make_bars("up",count=10)
    rows[-1]["timestamp"]=rows[-2]["timestamp"]
    with pytest.raises(ValueError,match="timestamps_not_strictly_increasing"):
        normalize_bars(rows)


def test_invalid_ohlc_envelope_rejected():
    rows=make_bars("up",count=10)
    rows[-1]["high"]=rows[-1]["low"]-1
    with pytest.raises(ValueError,match="invalid_ohlc_envelope"):
        normalize_bars(rows)


def test_volume_indicators_unavailable_when_volume_missing():
    s=snapshot("up",volume=False,quote=False,volume_semantics_qualified=True)
    assert s.indicators["vwap_20"].status=="UNAVAILABLE"
    assert s.indicators["mfi_14"].reason=="VENUE_VOLUME_UNAVAILABLE"
    assert s.indicators["rsi_14"].status=="READY"


def test_volume_data_is_disabled_without_venue_semantics_qualification():
    s=snapshot("up",volume=True,quote=True,volume_semantics_qualified=False)
    assert s.indicators["relative_volume_20"].reason=="VENUE_VOLUME_UNQUALIFIED"
    assert s.indicators["rsi_14"].status=="READY"


def test_vwap_requires_quote_volume_semantics():
    s=snapshot("up",volume=True,quote=False)
    assert s.indicators["relative_volume_20"].status=="READY"
    assert s.indicators["vwap_20"].reason=="VENUE_QUOTE_VOLUME_UNAVAILABLE"


def test_donchian_breakout_reference_excludes_current_candle():
    rows=make_bars("up",count=80)
    rows[-1]["high"]=rows[-2]["high"]+100
    b=normalize_bars(rows)
    ind=calculate_indicators(b)
    assert ind["donchian_upper_prior"].value==max(x.high for x in b[-21:-1])
    assert ind["donchian_upper_prior"].value < b[-1].high


def test_indicator_groups_do_not_count_correlated_indicators_as_votes():
    s=snapshot("up")
    assert s.families["trend"]["independent_vote_count"]==0
    assert s.families["momentum"]["independent_vote_count"]==0


def test_dashboard_payload_is_read_only_and_hash_bound():
    s=snapshot("up")
    payload=dashboard_payload(s,source="gateio_public_spot",input_sha256="a"*64)
    assert payload["status"]=="READ_ONLY_RESEARCH"
    assert all(v is False for v in payload["controls"].values())
    assert payload["regime"]["is_predictive_probability"] is False


def test_dashboard_rejects_invalid_provenance_digest():
    with pytest.raises(ValueError,match="invalid_input_sha256"):
        dashboard_payload(snapshot(),source="gateio",input_sha256="bad")


def test_unknown_parameters_rejected():
    with pytest.raises(ValueError,match="invalid_parameter_keys"):
        calculate_indicators(normalize_bars(make_bars()),{"magic":5})


def test_nonpositive_parameters_rejected():
    with pytest.raises(ValueError,match="invalid_parameter"):
        calculate_indicators(normalize_bars(make_bars()),{"rsi":0})


def test_market_identity_is_normalized_but_not_hardcoded():
    s=build_snapshot(make_bars(),venue="TEST-VENUE",market="equities",symbol="ABC",timeframe="1d")
    assert (s.venue,s.market,s.symbol,s.timeframe)==("test-venue","equities","ABC","1d")


def test_market_profile_config_keeps_volume_and_execution_fail_closed():
    config=json.loads((Path(__file__).resolve().parents[1]/"forward/universal_indicator_engine_v1.json").read_text())
    assert config["safety"]["execution_enabled"] is False
    assert config["safety"]["risk_gate_remains_independent_veto"] is True
    assert "DISABLED_UNLESS_PROVIDER_SEMANTICS_VALIDATED" in config["market_profiles"]["forex_spot"]["tick_volume"]
    assert config["selection_policy"]["correlated_indicators_count_as_independent_votes"] is False
    assert config["default_parameters"]==DEFAULT_PERIODS
    assert config["regime_profiles"]==REGIME_INDICATOR_PROFILES
    assert {k:v for k,v in config["regime_policy"].items() if k!="confidence_semantics"}==REGIME_POLICY
    assert {k:v for k,v in config["family_weights"].items() if k!="semantics"}==FAMILY_WEIGHTS


def test_transition_regime_is_a_valid_non_trade_state():
    s=snapshot("transition")
    assert s.regime.label in {"TRANSITION","BULLISH","BEARISH","RANGE"}
    assert s.decision_authority is False
    assert s.signal_generation_enabled is False
