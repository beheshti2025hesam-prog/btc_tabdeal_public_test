from datetime import datetime, timedelta, timezone

import pytest

from core.backtest.engine import BacktestEngine, BacktestSide, BacktestSignal
from core.data_engine.candles import Candle


UTC = timezone.utc
T0 = datetime(2026, 1, 1, tzinfo=UTC)


def candle(symbol, start_minute, *, low, high):
    start = T0 + timedelta(minutes=start_minute)
    return Candle(
        symbol=symbol,
        timeframe_seconds=60,
        start=start,
        end=start + timedelta(minutes=1),
        open=100.0,
        high=high,
        low=low,
        close=100.0,
        volume=1.0,
        trade_count=1,
    )


def test_symbol_scoped_signal_does_not_cross_into_another_market():
    candles = [
        candle("ETH_USDT", 1, low=80.0, high=120.0),
        candle("BTC_USDT", 1, low=99.0, high=101.0),
    ]
    signal = BacktestSignal(
        timestamp=T0,
        side=BacktestSide.LONG,
        entry_price=100.0,
        stop_price=95.0,
        target_price=110.0,
        symbol="BTC_USDT",
    )

    result = BacktestEngine().run(candles, [signal])

    assert result.trades == ()


def test_quantity_scales_pnl_and_fees_on_total_notional():
    candles = [candle("BTC_USDT", 1, low=99.0, high=110.0)]
    signal = BacktestSignal(
        timestamp=T0,
        side=BacktestSide.LONG,
        entry_price=100.0,
        stop_price=95.0,
        target_price=110.0,
        symbol="BTC_USDT",
        quantity=2.0,
    )

    result = BacktestEngine(fee_bps=10.0).run(candles, [signal])
    trade = result.trades[0]

    assert trade.gross_pnl == pytest.approx(20.0)
    assert trade.fees == pytest.approx(0.42)
    assert trade.net_pnl == pytest.approx(19.58)


def test_overlapping_signals_on_same_symbol_are_not_double_counted():
    candles = [
        candle("BTC_USDT", 1, low=99.0, high=101.0),
        candle("BTC_USDT", 2, low=99.0, high=110.0),
    ]
    signals = [
        BacktestSignal(
            timestamp=T0,
            side=BacktestSide.LONG,
            entry_price=100.0,
            stop_price=95.0,
            target_price=110.0,
            symbol="BTC_USDT",
        ),
        BacktestSignal(
            timestamp=T0 + timedelta(seconds=30),
            side=BacktestSide.LONG,
            entry_price=100.0,
            stop_price=95.0,
            target_price=110.0,
            symbol="BTC_USDT",
        ),
    ]

    result = BacktestEngine().run(candles, signals)

    assert len(result.trades) == 1
    assert result.trades[0].exit_reason == "TARGET"


def test_invalid_quantity_is_skipped_without_affecting_metrics():
    candles = [candle("BTC_USDT", 1, low=99.0, high=110.0)]
    signal = BacktestSignal(
        timestamp=T0,
        side=BacktestSide.LONG,
        entry_price=100.0,
        stop_price=95.0,
        target_price=110.0,
        symbol="BTC_USDT",
        quantity=0.0,
    )

    result = BacktestEngine().run(candles, [signal])

    assert result.trades == ()
    assert result.equity_curve == ()
