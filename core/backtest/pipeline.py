"""Mother Agent - research decision-to-backtest pipeline v1.0.

Research-only orchestration. It connects historical feature snapshots to the
strategy, signal contract, backtest adapter, and deterministic backtest engine.
No live execution or exchange connectivity is present.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Mapping, Sequence

from core.backtest.engine import BacktestEngine, BacktestResult, BacktestSignal
from core.backtest.signal_adapter import SignalBacktestAdapter
from core.data_engine.feature_engine import FeatureSnapshot
from core.signal.adapter import DecisionSignalAdapter
from core.signal.contract import SignalIntent, SignalMode, SignalRecord
from core.strategy.decision import StrategyDecisionEngine


@dataclass(frozen=True)
class DecisionBacktestResult:
    signals: tuple[SignalRecord, ...]
    backtest_signals: tuple[BacktestSignal, ...]
    result: BacktestResult


class DecisionBacktestPipeline:
    """Run historical snapshots through decision -> signal -> backtest.

    Entry/stop/target levels are supplied by the caller. This keeps strategy
    direction separate from position sizing/price-level policy and avoids
    inventing execution behavior inside the strategy layer.
    """

    def __init__(
        self,
        *,
        decision_engine: StrategyDecisionEngine | None = None,
        signal_adapter: DecisionSignalAdapter | None = None,
        backtest_adapter: SignalBacktestAdapter | None = None,
        backtest_engine: BacktestEngine | None = None,
        mode: SignalMode = SignalMode.SIGNAL_ONLY,
    ):
        if mode == SignalMode.ANALYSIS_ONLY:
            raise ValueError("ANALYSIS_ONLY cannot be converted into backtest signals")
        self.decision_engine = decision_engine or StrategyDecisionEngine()
        self.signal_adapter = signal_adapter or DecisionSignalAdapter()
        self.backtest_adapter = backtest_adapter or SignalBacktestAdapter()
        self.backtest_engine = backtest_engine or BacktestEngine()
        self.mode = mode

    def run(
        self,
        snapshots: Sequence[FeatureSnapshot],
        candles,
        *,
        levels_by_timestamp: Mapping[datetime, tuple[float, float, float]],
        quantity: float = 1.0,
    ) -> DecisionBacktestResult:
        self._validate_snapshots(snapshots)
        signals: list[SignalRecord] = []

        for snapshot in snapshots:
            decision = self.decision_engine.evaluate(snapshot)
            levels = levels_by_timestamp.get(snapshot.timestamp)
            if decision.decision.value != SignalIntent.NO_TRADE.value and levels is None:
                raise ValueError(
                    "actionable decision requires entry, stop, and target levels"
                )

            entry = stop = target = None
            if levels is not None:
                entry, stop, target = levels

            signal = self.signal_adapter.build(
                symbol=snapshot.symbol,
                timeframe_seconds=snapshot.timeframe_seconds,
                timestamp=snapshot.timestamp,
                decision=decision,
                mode=self.mode,
                entry_price=entry,
                stop_price=stop,
                target_price=target,
            )
            signals.append(signal)

        backtest_signals = self.backtest_adapter.build_many(
            signals,
            quantity=quantity,
        )
        result = self.backtest_engine.run(candles, backtest_signals)
        return DecisionBacktestResult(
            signals=tuple(signals),
            backtest_signals=backtest_signals,
            result=result,
        )

    @staticmethod
    def _validate_snapshots(snapshots: Sequence[FeatureSnapshot]) -> None:
        seen: set[tuple[str, datetime]] = set()
        for snapshot in snapshots:
            timestamp = snapshot.timestamp
            if timestamp is None or timestamp.tzinfo is None:
                raise ValueError("feature snapshot timestamp must be timezone-aware")
            if snapshot.timeframe_seconds <= 0:
                raise ValueError("feature snapshot timeframe must be positive")
            key = (snapshot.symbol, timestamp)
            if key in seen:
                raise ValueError("duplicate feature snapshot timestamp for symbol")
            seen.add(key)
