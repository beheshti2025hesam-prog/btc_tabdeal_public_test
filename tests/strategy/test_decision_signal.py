from datetime import datetime, timezone

import pytest

from core.data_engine.feature_engine import FeatureSnapshot
from core.signal.contract import SignalIntent, SignalMode
from core.strategy.baseline import Decision
from core.strategy.decision import FinalDecision
from core.strategy.decision_signal import DecisionSignalAdapter


TS = datetime(2026, 1, 1, tzinfo=timezone.utc)


def snapshot(timestamp=TS):
    return FeatureSnapshot(
        symbol="BTC_USDT",
        timeframe_seconds=900,
        close=100.0,
        ema=99.0,
        vwap=99.5,
        buy_sell_delta=2.0,
        buy_ratio=0.6,
        realized_volatility=0.01,
        average_true_range=1.0,
        volume_ratio=1.2,
        volume_spike=False,
        regime="uptrend",
        timestamp=timestamp,
    )


def test_actionable_decision_becomes_signal():
    decision = FinalDecision(Decision.LONG, ("confirmed",))
    signal = DecisionSignalAdapter().build(
        snapshot(),
        decision,
        entry_price=100.0,
        stop_price=97.0,
        target_price=109.0,
        confidence=0.8,
    )

    assert signal.intent == SignalIntent.LONG
    assert signal.mode == SignalMode.SIGNAL_ONLY
    assert signal.entry_price == 100.0
    assert signal.stop_price == 97.0
    assert signal.target_price == 109.0


def test_no_trade_never_carries_trade_geometry():
    decision = FinalDecision(Decision.NO_TRADE, ("quality_gate_rejected",))
    signal = DecisionSignalAdapter().build(
        snapshot(),
        decision,
        entry_price=100.0,
        stop_price=97.0,
        target_price=109.0,
    )

    assert signal.intent == SignalIntent.NO_TRADE
    assert signal.entry_price is None
    assert signal.stop_price is None
    assert signal.target_price is None


def test_actionable_decision_requires_explicit_geometry():
    decision = FinalDecision(Decision.SHORT, ("confirmed",))

    with pytest.raises(ValueError, match="entry, stop, and target"):
        DecisionSignalAdapter().build(snapshot(), decision)


def test_signal_timestamp_is_taken_from_feature_snapshot():
    decision = FinalDecision(Decision.LONG, ("confirmed",))
    signal = DecisionSignalAdapter().build(
        snapshot(),
        decision,
        entry_price=100.0,
        stop_price=97.0,
        target_price=109.0,
    )

    assert signal.timestamp == TS


def test_missing_snapshot_timestamp_fails_closed():
    decision = FinalDecision(Decision.LONG, ("confirmed",))

    with pytest.raises(ValueError, match="timestamp"):
        DecisionSignalAdapter().build(
            snapshot(timestamp=None),
            decision,
            entry_price=100.0,
            stop_price=97.0,
            target_price=109.0,
        )
