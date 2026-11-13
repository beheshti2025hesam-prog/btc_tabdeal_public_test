from datetime import datetime
from forward.range_opportunity_policy_v1 import RangeSnapshot, evaluate_range_candidate


def base(**changes):
    values = dict(symbol="BTC_USDT", timeframe="15m", candle_closed=True,
        observed_at=datetime.fromisoformat("2026-11-04T12:45:00+00:00"), open=99.8, high=100.3, low=98.5, close=100.2,
        prior_range_high=110.0, prior_range_low=100.0, atr14=2.0, adx14=14.0,
        range_persistence=0.85, adx14_1h=17.0, adx14_4h=16.0, ema50_slope_atr_1h=0.1, ema50_slope_atr_4h=-0.1,
        rsi14_previous=29.0, rsi14=37.0, mfi14_previous=25.0, mfi14=32.0,
        estimated_round_trip_cost_fraction=0.001)
    values.update(changes)
    return RangeSnapshot(**values)


def test_valid_long_sweep_reclaim_candidate():
    result = evaluate_range_candidate(base())
    assert result.state == "CANDIDATE"
    assert result.direction == "LONG"
    assert result.stop_loss < result.entry_reference < result.take_profit
    assert result.net_rr_estimate >= 1.2
    assert result.execution_enabled is False and result.orders_placed is False


def test_valid_short_sweep_reclaim_candidate():
    result = evaluate_range_candidate(base(open=110.2, high=111.5, low=109.8, close=109.9,
        rsi14_previous=71.0, rsi14=63.0, mfi14_previous=75.0, mfi14=66.0))
    assert result.state == "CANDIDATE"
    assert result.direction == "SHORT"
    assert result.take_profit < result.entry_reference < result.stop_loss


def test_open_candle_fails_closed():
    assert "CANDLE_NOT_CLOSED" in evaluate_range_candidate(base(candle_closed=False)).reasons


def test_no_trade_in_midrange_or_without_sweep():
    assert evaluate_range_candidate(base(open=105, high=106, low=104, close=105)).state == "NO_CANDIDATE"


def test_high_adx_or_directional_htf_blocks_range_setup():
    assert "TREND_STRENGTH_TOO_HIGH" in evaluate_range_candidate(base(adx14=25)).reasons
    assert "HTF_DIRECTIONAL_PRESSURE" in evaluate_range_candidate(base(ema50_slope_atr_4h=0.7)).reasons


def test_low_persistence_blocks_range_setup():
    assert "RANGE_NOT_PERSISTENT" in evaluate_range_candidate(base(range_persistence=0.5)).reasons


def test_costs_can_reject_apparently_good_geometry():
    result = evaluate_range_candidate(base(estimated_round_trip_cost_fraction=0.03))
    assert result.state == "NO_CANDIDATE"
    assert "NET_REWARD_TO_RISK_BELOW_FLOOR" in result.reasons


def test_nonfinite_and_invalid_ranges_fail_closed():
    assert evaluate_range_candidate(base(atr14=float("nan"))).state == "NO_CANDIDATE"
    assert evaluate_range_candidate(base(prior_range_high=99)).state == "NO_CANDIDATE"


def test_scope_and_direction_ambiguity_fail_closed():
    assert "SCOPE_MISMATCH" in evaluate_range_candidate(base(symbol="ETH_USDT")).reasons
    assert "NO_UNAMBIGUOUS_BOUNDARY_RECLAIM" in evaluate_range_candidate(base(
        high=111.5, low=98.5, close=105, open=105,
        rsi14_previous=50, rsi14=50, mfi14_previous=50, mfi14=50)).reasons
