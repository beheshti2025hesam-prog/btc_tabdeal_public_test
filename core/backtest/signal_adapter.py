"""Mother Agent - signal to backtest adapter v1.0.

This adapter is research-only: it converts an already-created SignalRecord
into a deterministic backtest intent. It never places or prepares live orders.
"""
from typing import Iterable

from core.backtest.engine import BacktestSide, BacktestSignal
from core.signal.contract import SignalIntent, SignalRecord


class SignalBacktestAdapter:
    """Translate non-executing signal records into backtest signals."""

    def build(self, signal: SignalRecord, *, quantity: float = 1.0) -> BacktestSignal | None:
        if signal.intent == SignalIntent.NO_TRADE:
            return None
        if signal.entry_price is None or signal.stop_price is None or signal.target_price is None:
            raise ValueError("actionable signal must contain entry, stop, and target prices")
        side = (
            BacktestSide.LONG
            if signal.intent == SignalIntent.LONG
            else BacktestSide.SHORT
        )
        return BacktestSignal(
            timestamp=signal.timestamp,
            side=side,
            entry_price=signal.entry_price,
            stop_price=signal.stop_price,
            target_price=signal.target_price,
            symbol=signal.symbol,
            quantity=quantity,
        )

    def build_many(
        self,
        signals: Iterable[SignalRecord],
        *,
        quantity: float = 1.0,
    ) -> tuple[BacktestSignal, ...]:
        built = []
        for signal in signals:
            result = self.build(signal, quantity=quantity)
            if result is not None:
                built.append(result)
        return tuple(built)
