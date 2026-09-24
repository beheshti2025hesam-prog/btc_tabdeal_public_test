"""Mother Agent - strategy decision to signal adapter v1.0."""
from core.signal.contract import SignalIntent, SignalMode, SignalRecord
from core.strategy.decision import FinalDecision
from core.strategy.baseline import Decision


class DecisionSignalAdapter:
    """Translate a strategy result into a non-executing signal record."""

    def build(
        self,
        *,
        symbol: str,
        timeframe_seconds: int,
        timestamp: object,
        decision: FinalDecision,
        mode: SignalMode = SignalMode.SIGNAL_ONLY,
        confidence: float | None = None,
        entry_price: float | None = None,
        stop_price: float | None = None,
        target_price: float | None = None,
    ) -> SignalRecord:
        intent = SignalIntent(decision.decision.value)
        if intent == SignalIntent.NO_TRADE:
            entry_price = stop_price = target_price = None
        return SignalRecord(
            symbol=symbol,
            timeframe_seconds=timeframe_seconds,
            timestamp=timestamp,
            mode=mode,
            intent=intent,
            confidence=confidence,
            reasons=decision.reasons,
            entry_price=entry_price,
            stop_price=stop_price,
            target_price=target_price,
        )
