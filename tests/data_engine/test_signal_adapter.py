from datetime import datetime, timezone

from core.signal.adapter import DecisionSignalAdapter
from core.signal.contract import SignalIntent, SignalMode
from core.strategy.baseline import Decision
from core.strategy.decision import FinalDecision


def test_adapter_maps_long_to_signal_without_execution():
    decision = FinalDecision(Decision.LONG, ("confirmed",))
    result = DecisionSignalAdapter().build(
        symbol="BTC_USDT",
        timeframe_seconds=900,
        timestamp=datetime.now(timezone.utc),
        decision=decision,
        mode=SignalMode.ASSISTIVE,
        confidence=0.8,
        entry_price=100,
        stop_price=99,
        target_price=103,
    )
    assert result.intent == SignalIntent.LONG
    assert result.mode == SignalMode.ASSISTIVE


def test_adapter_clears_prices_for_no_trade():
    decision = FinalDecision(Decision.NO_TRADE, ("blocked",))
    result = DecisionSignalAdapter().build(
        symbol="BTC_USDT",
        timeframe_seconds=900,
        timestamp=datetime.now(timezone.utc),
        decision=decision,
        entry_price=100,
        stop_price=99,
        target_price=103,
    )
    assert result.intent == SignalIntent.NO_TRADE
    assert result.entry_price is None
