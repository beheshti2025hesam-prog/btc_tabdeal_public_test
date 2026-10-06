"""Real-data POST-QUALITY-BASELINE historical pipeline.

This path never falls back to BaselineStrategy. If the causal evidence engine
cannot establish every required gate, the result is NO_TRADE.
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
from core.models.trade import CanonicalTrade
from core.risk.boundary import RiskDecision, RiskInput, RiskPolicy
from core.strategy.baseline import BaselineDecision
from core.strategy.quality_signal import PostQualityBaselineV2, QualitySignalInput
from core.feature_engine.quality_evidence import QualityEvidenceEngine


@dataclass(frozen=True)
class QualityRealDataBacktestResult:
    rows_read: int
    rows_valid: int
    rows_invalid: int
    candles: int
    observations: int
    continuity_excluded: int
    backtest: BacktestResult


class QualityRealDataBacktest:
    """Execution-free historical replay using POST-QUALITY gates only."""

    def __init__(self, csv_path: str, timeframe_seconds: int = 900,
                 equity: float = 1000.0):
        if timeframe_seconds <= 0:
            raise ValueError("timeframe_seconds must be positive")
        if equity <= 0:
            raise ValueError("equity must be positive")
        self.csv_path = csv_path
        self.timeframe_seconds = timeframe_seconds
        self.equity = equity
        self.signal = PostQualityBaselineV2()
        self.evidence = QualityEvidenceEngine()
        self.risk = RiskPolicy()

    def _load_trades(self) -> tuple[list[CanonicalTrade], int, int]:
        reader = RawDataReader(active_file=self.csv_path, archive_dir="__no_archive__")
        validator = RawDataValidator()
        normalizer = RawDataNormalizer()
        valid, total, invalid = [], 0, 0
        for row in reader.read_all():
            total += 1
            if validator.validate_row(row):
                invalid += 1
                continue
            valid.append(normalizer.normalize_row(row))
        valid.sort(key=lambda t: (t.timestamp, t.sequence or -1))
        return valid, total, invalid

    def run(self) -> QualityRealDataBacktestResult:
        trades, rows_read, rows_invalid = self._load_trades()
        candles = TradeCandleAggregator(self.timeframe_seconds).aggregate(trades)
        samples: list[BacktestSample] = []
        continuity_excluded = 0

        for index in range(1, len(candles) - 1):
            candle, next_candle = candles[index], candles[index + 1]
            if candle.symbol != next_candle.symbol:
                continue
            if next_candle.start != candle.end:
                continuity_excluded += 1
                continue

            ev = self.evidence.build(candles, index)
            direction = None
            if ev.htf_trend in ("long", "short") and ev.structure_bias == ev.htf_trend:
                direction = ev.htf_trend
            elif ev.structure_break_confirmed and ev.liquidity_event_confirmed:
                direction = "long" if candle.close > candle.open else "short"

            result = self.signal.evaluate(QualitySignalInput(
                data_valid=True,
                direction=direction,
                htf_trend=ev.htf_trend,
                htf_alignment=ev.htf_alignment,
                structure_bias=ev.structure_bias,
                structure_break_confirmed=ev.structure_break_confirmed,
                location_valid=ev.location_valid,
                liquidity_event_confirmed=ev.liquidity_event_confirmed,
                entry_trigger_confirmed=ev.entry_trigger_confirmed,
                displacement_confirmed=ev.displacement_confirmed,
                momentum_confirmed=ev.momentum_confirmed,
                participation_confirmed=ev.participation_confirmed,
                contradiction=ev.contradiction,
                stop_valid=ev.stop_valid,
                rr=ev.rr,
            ))

            decision = (
                BaselineDecision.LONG if result.decision.value == "LONG"
                else BaselineDecision.SHORT if result.decision.value == "SHORT"
                else BaselineDecision.NO_TRADE
            )
            risk = self.risk.evaluate(RiskInput(decision=decision, equity=self.equity))
            samples.append(BacktestSample(
                timestamp=candle.end,
                decision=decision,
                risk=risk,
                entry_price=candle.close,
                exit_price=next_candle.close,
            ))

        observations = [
            HistoricalObservation(timestamp=s.timestamp, sample=s) for s in samples
        ]
        self._last_observations = tuple(observations)
        backtest = HistoricalValidation().run(observations)
        return QualityRealDataBacktestResult(
            rows_read=rows_read,
            rows_valid=len(trades),
            rows_invalid=rows_invalid,
            candles=len(candles),
            observations=len(observations),
            continuity_excluded=continuity_excluded,
            backtest=backtest,
        )

    def run_walk_forward(self, train_size: int, test_size: int,
                         step_size: int | None = None,
                         embargo_size: int = 0) -> WalkForwardResult:
        self.run()
        return WalkForwardValidation(
            train_size=train_size,
            test_size=test_size,
            step_size=step_size,
            embargo_size=embargo_size,
        ).run(self._last_observations)
