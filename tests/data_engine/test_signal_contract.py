from datetime import datetime, timezone

import pytest

from core.signal.contract import SignalIntent, SignalMode, SignalRecord


def test_signal_only_record_has_no_execution_semantics():
    record = SignalRecord(
        symbol="BTC_USDT",
        timeframe_seconds=900,
        timestamp=datetime.now(timezone.utc),
        mode=SignalMode.SIGNAL_ONLY,
        intent=SignalIntent.LONG,
        confidence=0.75,
        reasons=("price_above_ema",),
        entry_price=100,
        stop_price=99,
        target_price=103,
    )
    assert record.intent == SignalIntent.LONG


def test_no_trade_cannot_carry_trade_prices():
    with pytest.raises(ValueError):
        SignalRecord(
            symbol="BTC_USDT",
            timeframe_seconds=900,
            timestamp=datetime.now(timezone.utc),
            mode=SignalMode.ANALYSIS_ONLY,
            intent=SignalIntent.NO_TRADE,
            confidence=None,
            reasons=("insufficient_confirmation",),
            entry_price=100,
        )


def test_confidence_is_bounded():
    with pytest.raises(ValueError):
        SignalRecord(
            symbol="BTC_USDT",
            timeframe_seconds=900,
            timestamp=datetime.now(timezone.utc),
            mode=SignalMode.ASSISTIVE,
            intent=SignalIntent.SHORT,
            confidence=1.2,
            reasons=(),
        )
