from datetime import datetime, timedelta, timezone

from core.backtest.engine import BacktestEngine, BacktestSide, BacktestSignal
from core.data_engine.candles import Candle


def candle(start_minute: int, o: float, h: float, l: float, c: float) -> Candle:
    start = datetime(2026, 1, 1, 0, start_minute, tzinfo=timezone.utc)
    return Candle("BTC_USDT", 60, start, start + timedelta(minutes=1), o, h, l, c, 1.0, 1)


def test_long_target_and_metrics():
    candles = [
        candle(0, 100, 101, 99, 100),
        candle(1, 100, 104, 100, 103),
    ]
    signal = BacktestSignal(
        timestamp=candles[0].start,
        side=BacktestSide.LONG,
        entry_price=100,
        stop_price=98,
        target_price=103,
    )
    result = BacktestEngine().run(candles, [signal])
    assert len(result.trades) == 1
    assert result.trades[0].exit_reason == "TARGET"
    assert result.trades[0].net_pnl == 3
    assert result.metrics.wins == 1


def test_both_stop_and_target_same_candle_is_conservatively_stop():
    candles = [
        candle(0, 100, 100, 100, 100),
        candle(1, 100, 105, 95, 100),
    ]
    signal = BacktestSignal(
        timestamp=candles[0].start,
        side=BacktestSide.LONG,
        entry_price=100,
        stop_price=98,
        target_price=104,
    )
    result = BacktestEngine().run(candles, [signal])
    assert result.trades[0].exit_reason == "STOP"
    assert result.trades[0].net_pnl == -2


def test_invalid_direction_is_not_simulated():
    candles = [candle(0, 100, 101, 99, 100), candle(1, 100, 102, 99, 101)]
    signal = BacktestSignal(
        timestamp=candles[0].start,
        side=BacktestSide.SHORT,
        entry_price=100,
        stop_price=98,
        target_price=105,
    )
    result = BacktestEngine().run(candles, [signal])
    assert result.trades == ()


def test_fees_and_slippage_are_applied():
    candles = [
        candle(0, 100, 101, 99, 100),
        candle(1, 100, 104, 100, 103),
    ]
    signal = BacktestSignal(
        timestamp=candles[0].start,
        side=BacktestSide.LONG,
        entry_price=100,
        stop_price=98,
        target_price=103,
    )
    result = BacktestEngine(fee_bps=10, slippage_bps=10).run(candles, [signal])
    assert result.trades[0].entry_price == 100.1
    assert result.trades[0].exit_price == 102.9
    assert result.trades[0].net_pnl < result.trades[0].gross_pnl
