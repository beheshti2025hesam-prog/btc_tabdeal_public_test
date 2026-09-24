"""Mother Agent - deterministic experiment runner v1.0.

Research-only orchestration:
ExperimentSpec -> walk-forward isolation -> decision pipeline -> backtest
-> evaluation. No secrets, exchange connectivity, or live execution.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Mapping, Sequence

from core.backtest.pipeline import DecisionBacktestPipeline, DecisionBacktestResult
from core.backtest.walk_forward import WalkForwardRun, WalkForwardRunner, WalkForwardSplitter
from core.data_engine.candles import Candle
from core.data_engine.feature_engine import FeatureSnapshot
from core.evaluation.metrics import EvaluationMetrics, EvaluationMetricsCalculator
from core.experiments.contract import ExperimentSpec


@dataclass(frozen=True)
class ExperimentWindowResult:
    """Deterministic result for one isolated test window."""

    index: int
    train_size: int
    test_size: int
    train_end: datetime | None
    test_start: datetime | None
    test_end: datetime | None
    result: DecisionBacktestResult


@dataclass(frozen=True)
class ExperimentResult:
    """Reproducible aggregate result for a research experiment."""

    experiment_id: str
    runs: tuple[ExperimentWindowResult, ...]
    metrics: EvaluationMetrics


class ExperimentRunner:
    """Run a FeatureSnapshot experiment without allowing test leakage.

    Train snapshots are passed to the walk-forward evaluator for isolation and
    future extensibility, but v1's stateless decision pipeline only evaluates
    the test snapshots. Candles are clipped to each test window so a signal
    cannot exit against candles belonging to a later window.
    """

    def __init__(
        self,
        spec: ExperimentSpec,
        *,
        splitter: WalkForwardSplitter,
        pipeline: DecisionBacktestPipeline | None = None,
        starting_capital: float = 1.0,
    ):
        if starting_capital <= 0:
            raise ValueError("starting_capital must be positive")
        self.spec = spec
        self.runner = WalkForwardRunner(splitter)
        self.pipeline = pipeline or DecisionBacktestPipeline()
        self.starting_capital = starting_capital

    def run(
        self,
        snapshots: Sequence[FeatureSnapshot],
        candles: Sequence[Candle],
        *,
        levels_by_timestamp: Mapping[datetime, tuple[float, float, float]],
        quantity: float = 1.0,
    ) -> ExperimentResult:
        self._validate_inputs(snapshots, candles, levels_by_timestamp)

        def evaluate(train, test):
            del train  # Reserved for future train/fit stages; never mixed into test.
            test_timestamps = {snapshot.timestamp for snapshot in test}
            test_end = test[-1].timestamp
            horizon = test_end + timedelta(seconds=test[-1].timeframe_seconds)
            test_candles = tuple(
                candle
                for candle in candles
                if candle.end <= horizon
                and candle.end > test[0].timestamp
            )
            test_levels = {
                timestamp: levels_by_timestamp[timestamp]
                for timestamp in test_timestamps
                if timestamp in levels_by_timestamp
            }
            return self.pipeline.run(
                test,
                test_candles,
                levels_by_timestamp=test_levels,
                quantity=quantity,
            )

        walk_runs = self.runner.run(snapshots, evaluate)
        window_results = tuple(
            ExperimentWindowResult(
                index=run.index,
                train_size=run.train_size,
                test_size=run.test_size,
                train_end=run.train_end,
                test_start=run.test_start,
                test_end=run.test_end,
                result=run.result,
            )
            for run in walk_runs
        )

        pnls = [
            trade.net_pnl
            for run in window_results
            for trade in run.result.result.trades
        ]
        metrics = EvaluationMetricsCalculator().calculate(
            pnls,
            starting_capital=self.starting_capital,
        )
        return ExperimentResult(
            experiment_id=self.spec.experiment_id,
            runs=window_results,
            metrics=metrics,
        )

    @staticmethod
    def _validate_inputs(
        snapshots: Sequence[FeatureSnapshot],
        candles: Sequence[Candle],
        levels_by_timestamp: Mapping[datetime, tuple[float, float, float]],
    ) -> None:
        if not snapshots:
            raise ValueError("snapshots must not be empty")
        if not candles:
            raise ValueError("candles must not be empty")

        for snapshot in snapshots:
            if snapshot.timestamp is None or snapshot.timestamp.tzinfo is None:
                raise ValueError("feature snapshot timestamp must be timezone-aware")

        for candle in candles:
            if candle.start.tzinfo is None or candle.end.tzinfo is None:
                raise ValueError("candle timestamps must be timezone-aware")

        for timestamp, levels in levels_by_timestamp.items():
            if timestamp.tzinfo is None:
                raise ValueError("level timestamp must be timezone-aware")
            if len(levels) != 3:
                raise ValueError("price levels must contain entry, stop, and target")
