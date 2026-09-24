from datetime import datetime, timedelta, timezone

import pytest

from core.backtest.engine import BacktestEngine
from core.backtest.pipeline import DecisionBacktestPipeline
from core.data_engine.feature_engine import FeatureSnapshot


UTC = timezone.utc
T0 = datetime(2026, 1, 1, tzinfo=UTC)


def snapshot(minute, *, close=101.0):
    return FeatureSnapshot(
        symbol="BTC_USDT",
        timeframe_seconds=60,
        close=close,
        ema=100.0,
        vwap=100.0,
        buy_sell_delta=1.0,
        buy_ratio=0.7,
        realized_volatility=0.01,
        average_true_range=1.0,
        volume_ratio=1.5,
        volume_spike=True,
        regime="uptrend",
        timestamp=T0 + timedelta(minutes=minute),
    )


def candle(minute, *, low=100.0, high=111.0):
    from core.data_engine.candles import Candle

    start = T0 + timedelta(minutes=minute)
    return Candle(
        symbol="BTC_USDT",
        timeframe_seconds=60,
        start=start,
        end=start + timedelta(minutes=1),
        open=101.0,
        high=high,
        low=low,
        close=105.0,
        volume=10.0,
        trade_count=1,
    )


def test_decision_to_signal_to_backtest_pipeline_is_research_only():
    result = DecisionBacktestPipeline(
        backtest_engine=BacktestEngine(),
    ).run(
        [snapshot(0)],
        [candle(1)],
        levels_by_timestamp={T0: (101.0, 95.0, 110.0)},
    )

    assert len(result.signals) == 1
    assert result.signals[0].intent.value == "LONG"
    assert len(result.backtest_signals) == 1
    assert result.result.trades[0].exit_reason == "TARGET"


def test_no_trade_does_not_require_price_levels():
    result = DecisionBacktestPipeline().run(
        [snapshot(0, close=99.0)],
        [candle(1)],
        levels_by_timestamp={},
    )

    assert result.signals[0].intent.value == "NO_TRADE"
    assert result.backtest_signals == ()
    assert result.result.trades == ()


def test_actionable_decision_without_levels_is_rejected():
    with pytest.raises(ValueError, match="actionable decision requires"):
        DecisionBacktestPipeline().run(
            [snapshot(0)],
            [candle(1)],
            levels_by_timestamp={},
        )


def test_naive_snapshot_timestamp_is_rejected():
    naive = FeatureSnapshot(
        symbol="BTC_USDT",
        timeframe_seconds=60,
        close=101.0,
        ema=100.0,
        vwap=100.0,
        buy_sell_delta=1.0,
        buy_ratio=0.7,
        realized_volatility=0.01,
        average_true_range=1.0,
        volume_ratio=1.5,
        volume_spike=True,
        regime="uptrend",
        timestamp=datetime(2026, 1, 1),
    )

    with pytest.raises(ValueError, match="timezone-aware"):
        DecisionBacktestPipeline().run(
            [naive],
            [candle(1)],
            levels_by_timestamp={},
        )


def test_analysis_only_cannot_enter_backtest_path():
    from core.signal.contract import SignalMode

    with pytest.raises(ValueError, match="ANALYSIS_ONLY"):
        DecisionBacktestPipeline(mode=SignalMode.ANALYSIS_ONLY)


def test_duplicate_snapshot_timestamp_is_rejected():
    with pytest.raises(ValueError, match="duplicate feature snapshot"):
        DecisionBacktestPipeline().run(
            [snapshot(0), snapshot(0)],
            [candle(1)],
            levels_by_timestamp={T0: (101.0, 95.0, 110.0)},
        )
