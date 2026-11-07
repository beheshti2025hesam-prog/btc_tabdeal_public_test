import dataclasses

import pytest

from forward.strategy_family_router_v1 import (
    RANGE_MEAN_REVERSION_RESEARCH_V1,
    ROUTER_VERSION,
    TREND_BREAKOUT_V2,
    route_strategy_family,
)


def route(regime="UPTREND", timeframe="15m", source="gateio_public_spot", symbol="BTC_USDT"):
    return route_strategy_family(source=source, symbol=symbol, timeframe=timeframe, regime=regime)


@pytest.mark.parametrize("regime", ["UPTREND", "DOWNTREND"])
def test_directional_regimes_route_to_frozen_trend_family_without_authority(regime):
    result = route(regime=regime)
    assert result.family_id == "trend_breakout"
    assert result.family_version == TREND_BREAKOUT_V2.version
    assert result.activation_state == "CANDIDATE_LOCKED_NOT_ACTIVE"
    assert result.state == "FAMILY_IDENTIFIED_NOT_AUTHORIZED"
    assert result.candidate_generation_authorized is False
    assert result.execution_enabled is False
    assert result.orders_placed is False


def test_range_routes_to_research_only_family_not_an_active_signal_path():
    result = route(regime="RANGE")
    assert result.family_id == "range_mean_reversion"
    assert result.family_version == RANGE_MEAN_REVERSION_RESEARCH_V1.version
    assert result.activation_state == "RESEARCH_ONLY_NOT_ACTIVE"
    assert result.candidate_generation_authorized is False
    assert result.execution_enabled is False
    assert result.orders_placed is False


@pytest.mark.parametrize(
    "kwargs,reason",
    [
        ({"source": "tabdeal_broadcast"}, "NON_CANONICAL_MARKET_DATA_SOURCE"),
        ({"symbol": "ETH_USDT"}, "SYMBOL_OUT_OF_V1_SCOPE"),
        ({"timeframe": "1m"}, "PRECISION_TIMEFRAME_CANNOT_GENERATE_SETUP"),
        ({"timeframe": "4h"}, "TIMEFRAME_OUT_OF_V1_SCOPE"),
    ],
)
def test_noncanonical_context_fails_closed(kwargs, reason):
    args = {"source": "gateio_public_spot", "symbol": "BTC_USDT", "timeframe": "15m", "regime": "UPTREND"}
    args.update(kwargs)
    result = route_strategy_family(**args)
    assert result.state == "NO_FAMILY"
    assert result.family_id is None
    assert result.reason_codes == (reason,)
    assert result.candidate_generation_authorized is False


def test_unknown_and_unclassified_regimes_do_not_fall_back_to_trend():
    for regime in ("UNKNOWN", "TRANSITION", "VOLATILE", "", None):
        result = route(regime=regime)
        assert result.state == "NO_FAMILY"
        assert result.family_id is None
        assert result.reason_codes == ("REGIME_HAS_NO_APPROVED_FAMILY",)


def test_family_profiles_are_immutable_and_never_enable_signals_or_execution():
    for profile in (TREND_BREAKOUT_V2, RANGE_MEAN_REVERSION_RESEARCH_V1):
        assert profile.signal_generation_enabled is False
        assert profile.execution_enabled is False
        assert profile.orders_placed is False
        with pytest.raises(dataclasses.FrozenInstanceError):
            profile.execution_enabled = True


def test_trend_profile_keeps_existing_three_r_floor_and_gate_contract():
    assert TREND_BREAKOUT_V2.minimum_rr == 3.0
    assert "CLOSED_15M_20_BAR_BREAKOUT" in TREND_BREAKOUT_V2.required_gates
    assert "INDEPENDENT_RISK_GATE" in TREND_BREAKOUT_V2.required_gates
    assert TREND_BREAKOUT_V2.activation_state == "CANDIDATE_LOCKED_NOT_ACTIVE"


def test_range_profile_does_not_claim_an_approved_rr_or_edge():
    assert RANGE_MEAN_REVERSION_RESEARCH_V1.minimum_rr is None
    assert RANGE_MEAN_REVERSION_RESEARCH_V1.activation_state == "RESEARCH_ONLY_NOT_ACTIVE"
    assert "INDEPENDENT_OUT_OF_SAMPLE_ACCEPTANCE" in RANGE_MEAN_REVERSION_RESEARCH_V1.required_gates


def test_serialized_route_carries_explicit_safety_boundary():
    payload = route(regime="RANGE").as_dict()
    assert payload["router_version"] == ROUTER_VERSION
    assert payload["candidate_generation_authorized"] is False
    assert payload["execution_enabled"] is False
    assert payload["orders_placed"] is False
