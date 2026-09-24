"""Mother Agent - strategy decision to signal adapter v1.0.

This boundary converts a deterministic strategy decision into the neutral
SignalRecord contract. It does not execute trades or connect to a venue.
"""

from core.data_engine.feature_engine import FeatureSnapshot
from core.signal.contract import SignalIntent, SignalMode, SignalRecord
from core.strategy.decision import FinalDecision
from core.strategy.baseline import Decision


class DecisionSignalAdapter:
    """Translate a FinalDecision plus explicit trade geometry into a signal."""

    def build(
        self,
        snapshot: FeatureSnapshot,
        decision: FinalDecision,
        *,
        mode: SignalMode = SignalMode.SIGNAL_ONLY,
        confidence: float | None = None,
        entry_price: float | None = None,
        stop_price: float | None = None,
        target_price: float | None = None,
    ) -> SignalRecord:
        timestamp = snapshot.timestamp
        if timestamp is None:
            raise ValueError("snapshot timestamp is required")

        if decision.decision == Decision.NO_TRADE:
            return SignalRecord(
                symbol=snapshot.symbol,
                timeframe_seconds=snapshot.timeframe_seconds,
                timestamp=timestamp,
                mode=mode,
                intent=SignalIntent.NO_TRADE,
                confidence=confidence,
                reasons=decision.reasons,
            )

        geometry = (entry_price, stop_price, target_price)
        if any(value is None for value in geometry):
            raise ValueError(
                "actionable decision requires entry, stop, and target prices"
            )

        intent = (
            SignalIntent.LONG
            if decision.decision == Decision.LONG
            else SignalIntent.SHORT
        )
        return SignalRecord(
            symbol=snapshot.symbol,
            timeframe_seconds=snapshot.timeframe_seconds,
            timestamp=timestamp,
            mode=mode,
            intent=intent,
            confidence=confidence,
            reasons=decision.reasons,
            entry_price=entry_price,
            stop_price=stop_price,
            target_price=target_price,
        )
