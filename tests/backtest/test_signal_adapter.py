from datetime import datetime, timezone

import pytest

from core.backtest.engine import BacktestSide
from core.backtest.signal_adapter import SignalBacktestAdapter
from core.signal.contract import SignalIntent, SignalMode, SignalRecord


def signal(intent, **prices):
    return SignalRecord(
        symbol="BTC_USDT",
        timeframe_seconds=900,
        timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
        mode=SignalMode.SIGNAL_ONLY,
        intent=intent,
        confidence=0.8,
        reasons=("test",),
        **prices,
    )


def test_actionable_signal_maps_to_backtest_intent():
    result = SignalBacktestAdapter().build(
        signal(
            SignalIntent.LONG,
            entry_price=100.0,
            stop_price=95.0,
            target_price=110.0,
        ),
        quantity=2.5,
    )

    assert result is not None
    assert result.side == BacktestSide.LONG
    assert result.symbol == "BTC_USDT"
    assert result.quantity == 2.5


def test_no_trade_is_not_backtested():
    result = SignalBacktestAdapter().build(signal(SignalIntent.NO_TRADE))

    assert result is None


def test_actionable_signal_requires_trade_geometry():
    with pytest.raises(ValueError, match="entry, stop, and target"):
        SignalBacktestAdapter().build(
            signal(SignalIntent.SHORT, entry_price=100.0, stop_price=105.0)
        )


def test_build_many_filters_no_trade_signals():
    adapter = SignalBacktestAdapter()
    result = adapter.build_many(
        [
            signal(SignalIntent.NO_TRADE),
            signal(
                SignalIntent.SHORT,
                entry_price=100.0,
                stop_price=105.0,
                target_price=90.0,
            ),
        ]
    )

    assert len(result) == 1
    assert result[0].side == BacktestSide.SHORT
