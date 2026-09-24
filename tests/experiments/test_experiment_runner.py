from datetime import datetime, timedelta, timezone

import pytest

from core.backtest.walk_forward import WalkForwardSplitter
from core.experiments.contract import ExperimentSpec
from core.experiments.runner import ExperimentRunner
from core.data_engine.candles import Candle
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


def candle(minute, *, high=111.0, low=100.0):
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


def spec():
    return ExperimentSpec(
        name="baseline",
        version="1",
        dataset_id="test-dataset",
        strategy_id="baseline-v1",
        timeframe_seconds=60,
    )


def test_experiment_runner_connects_walk_forward_pipeline_and_evaluation():
    result = ExperimentRunner(
        spec(),
        splitter=WalkForwardSplitter(train_size=1, test_size=1),
    ).run(
        [snapshot(0), snapshot(1)],
        [candle(1)],
        levels_by_timestamp={T0 + timedelta(minutes=1): (101.0, 95.0, 110.0)},
    )

    assert result.experiment_id == spec().experiment_id
    assert len(result.runs) == 1
    assert result.runs[0].result.signals[0].intent.value == "LONG"
    assert result.metrics.trades == 1
    assert result.metrics.wins == 1
    assert result.metrics.net_pnl == 9.0


def test_experiment_runner_does_not_use_candles_after_test_horizon():
    result = ExperimentRunner(
        spec(),
        splitter=WalkForwardSplitter(train_size=1, test_size=1),
    ).run(
        [snapshot(0), snapshot(1)],
        [candle(2)],
        levels_by_timestamp={T0 + timedelta(minutes=1): (101.0, 95.0, 110.0)},
    )

    assert result.metrics.trades == 0
    assert result.runs[0].result.result.trades == ()


def test_experiment_runner_rejects_naive_candle_timestamp():
    bad = Candle(
        symbol="BTC_USDT",
        timeframe_seconds=60,
        start=datetime(2026, 1, 1, 0, 1),
        end=datetime(2026, 1, 1, 0, 2),
        open=101.0,
        high=111.0,
        low=100.0,
        close=105.0,
        volume=10.0,
        trade_count=1,
    )

    with pytest.raises(ValueError, match="timezone-aware"):
        ExperimentRunner(
            spec(),
            splitter=WalkForwardSplitter(train_size=1, test_size=1),
        ).run(
            [snapshot(0), snapshot(1)],
            [bad],
            levels_by_timestamp={},
        )


def test_experiment_runner_requires_starting_capital():
    with pytest.raises(ValueError, match="starting_capital"):
        ExperimentRunner(
            spec(),
            splitter=WalkForwardSplitter(train_size=1, test_size=1),
            starting_capital=0,
        )
