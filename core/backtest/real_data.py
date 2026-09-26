"""Execution-free real-data historical pipeline.

Reads raw BTC/USDT CSV data through the existing Data Foundation contracts,
derives 1-minute features using only information available at each candle
close, creates baseline/risk decisions, and evaluates the next candle as the
realized outcome. No orders, capital mutation, leverage, or live execution.
"""
from dataclasses import dataclass
from typing import Iterable

from core.backtest.engine import BacktestSample, BacktestResult
from core.backtest.validation import HistoricalObservation, HistoricalValidation
from core.backtest.walk_forward import WalkForwardResult, WalkForwardValidation
from core.data_engine.candles import TradeCandleAggregator
from core.data_engine.normalizer import RawDataNormalizer
from core.data_engine.reader import RawDataReader
from core.data_engine.validator import RawDataValidator
from core.feature_engine.ema import EMACalculator
from core.feature_engine.adapter import IntelligenceFeatureInput
from core.feature_engine.boundary import FeatureBoundaryGate
from core.data_engine.vwap import VWAPCalculator
from core.models.trade import CanonicalTrade
from core.risk.boundary import RiskDecision, RiskInput, RiskPolicy
from core.strategy.baseline import BaselineStrategy, BaselineStrategyInput


@dataclass(frozen=True)
class RealDataBacktestResult:
    rows_read: int
    rows_valid: int
    rows_invalid: int
    candles: int
    observations: int
    continuity_excluded: int
    backtest: BacktestResult


class RealDataBacktest:
    """Run a deterministic, read-only historical pipeline over a CSV file."""

    def __init__(
        self,
        csv_path: str,
        timeframe_seconds: int = 60,
        ema_period: int = 20,
        equity: float = 1000.0,
    ) -> None:
        if timeframe_seconds <= 0:
            raise ValueError("timeframe_seconds must be positive")
        if ema_period <= 0:
            raise ValueError("ema_period must be positive")
        if equity <= 0:
            raise ValueError("equity must be positive")
        self.csv_path = csv_path
        self.timeframe_seconds = timeframe_seconds
        self.ema_period = ema_period
        self.equity = equity

    def _load_trades(self) -> tuple[list[CanonicalTrade], int, int]:
        reader = RawDataReader(active_file=self.csv_path, archive_dir="__no_archive__")
        validator = RawDataValidator()
        normalizer = RawDataNormalizer()
        valid: list[CanonicalTrade] = []
        total = invalid = 0

        for row in reader.read_all():
            total += 1
            if validator.validate_row(row):
                invalid += 1
                continue
            valid.append(normalizer.normalize_row(row))

        return valid, total, invalid

    def _pressure_by_candle(
        self, trades: Iterable[CanonicalTrade]
    ) -> dict[tuple[str, int], tuple[float, float]]:
        groups: dict[tuple[str, int], list[CanonicalTrade]] = {}
        for trade in trades:
            epoch = int(trade.timestamp.timestamp())
            bucket_epoch = epoch - (epoch % self.timeframe_seconds)
            key = (trade.symbol, bucket_epoch)
            groups.setdefault(key, []).append(trade)

        result: dict[tuple[str, int], tuple[float, float]] = {}
        for key, group in groups.items():
            buy = sum(t.quantity for t in group if t.side == "buy")
            sell = sum(t.quantity for t in group if t.side == "sell")
            total = buy + sell
            result[key] = (
                buy / total if total else 0.0,
                buy - sell,
            )
        return result

    def run(self) -> RealDataBacktestResult:
        trades, rows_read, rows_invalid = self._load_trades()
        trades.sort(key=lambda t: (t.timestamp, t.sequence or -1))

        candles = TradeCandleAggregator(self.timeframe_seconds).aggregate(trades)
        ema = EMACalculator(self.ema_period).calculate(candles)
        vwap = VWAPCalculator(self.timeframe_seconds).calculate(trades)
        pressure = self._pressure_by_candle(trades)

        ema_by_end = {(item.symbol, item.timestamp): item for item in ema}
        vwap_by_end = {(item.symbol, item.end): item for item in vwap}

        samples: list[BacktestSample] = []
        continuity_excluded = 0
        strategy = BaselineStrategy(min_confirmations=3)
        risk = RiskPolicy()

        for index in range(self.ema_period - 1, len(candles) - 1):
            candle = candles[index]
            next_candle = candles[index + 1]
            if candle.symbol != next_candle.symbol:
                continue
            if next_candle.start != candle.end:
                continuity_excluded += 1
                continue

            bucket_epoch = int(candle.start.timestamp())
            key = (candle.symbol, bucket_epoch)
            buy_ratio, delta = pressure.get(key, (None, None))
            ema_item = ema_by_end.get((candle.symbol, candle.end))
            vwap_item = vwap_by_end.get((candle.symbol, candle.end))
            if ema_item is None or vwap_item is None or buy_ratio is None:
                continue

            boundary = FeatureBoundaryGate().evaluate(
                IntelligenceFeatureInput(
                    candle=candle,
                    ema=ema_item,
                    vwap=vwap_item,
                    buy_sell_delta=delta,
                    buy_ratio=buy_ratio,
                )
            )
            if not boundary.passed or boundary.snapshot is None:
                continue

            decision = strategy.evaluate(
                BaselineStrategyInput(features=boundary.snapshot)
            )
            risk_decision = risk.evaluate(
                RiskInput(decision=decision, equity=self.equity)
            )
            samples.append(
                BacktestSample(
                    timestamp=candle.end,
                    decision=decision,
                    risk=risk_decision,
                    entry_price=candle.close,
                    exit_price=next_candle.close,
                )
            )

        observations = [
            HistoricalObservation(timestamp=sample.timestamp, sample=sample)
            for sample in samples
        ]
        self._last_observations = tuple(observations)
        backtest = HistoricalValidation().run(observations)
        return RealDataBacktestResult(
            rows_read=rows_read,
            rows_valid=len(trades),
            rows_invalid=rows_invalid,
            candles=len(candles),
            observations=len(observations),
            continuity_excluded=continuity_excluded,
            backtest=backtest,
        )

    def run_walk_forward(
        self,
        train_size: int,
        test_size: int,
        step_size: int | None = None,
        embargo_size: int = 0,
    ) -> WalkForwardResult:
        """Run strict OOS walk-forward measurement on this real-data pipeline.

        The baseline currently has no learned parameters; the train window is
        therefore retained as a temporal provenance boundary and is not used
        for tuning.
        """
        self.run()
        return WalkForwardValidation(
            train_size=train_size,
            test_size=test_size,
            step_size=step_size,
            embargo_size=embargo_size,
        ).run(self._last_observations)
