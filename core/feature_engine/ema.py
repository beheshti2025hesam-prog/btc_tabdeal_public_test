"""HES Trade Agent - Exponential Moving Average feature.

Feature Engine v1.0: deterministic EMA derived from canonical Data Intelligence candles.
This module computes descriptive features only; it does not emit trading signals or execute orders.
"""
from dataclasses import dataclass
from datetime import datetime
from math import isfinite
from typing import Iterable, List

from core.data_engine.candles import Candle


@dataclass(frozen=True)
class EMASnapshot:
    symbol: str
    timeframe_seconds: int
    period: int
    timestamp: datetime
    value: float


class EMACalculator:
    """Calculate deterministic EMA snapshots from candle closes."""

    def __init__(self, period: int = 20):
        if period <= 0:
            raise ValueError("period must be positive")
        self.period = period

    def calculate(self, candles: Iterable[Candle]) -> List[EMASnapshot]:
        groups = {}
        for candle in candles:
            if not candle.symbol:
                raise ValueError("candle symbol must be non-empty")
            if candle.timeframe_seconds <= 0:
                raise ValueError("candle timeframe_seconds must be positive")
            if (candle.start.tzinfo is None or candle.start.utcoffset() is None or
                    candle.end.tzinfo is None or candle.end.utcoffset() is None):
                raise ValueError("candle timestamps must be timezone-aware")
            if not isfinite(candle.close):
                raise ValueError("candle close must be finite")
            groups.setdefault((candle.symbol, candle.timeframe_seconds), []).append(candle)

        results: List[EMASnapshot] = []
        for (symbol, timeframe_seconds), group in groups.items():
            ordered = sorted(group, key=lambda candle: candle.start)
            if len(ordered) < self.period:
                continue

            seed = sum(candle.close for candle in ordered[: self.period]) / self.period
            if not isfinite(seed):
                raise ValueError("EMA seed must be finite")

            alpha = 2.0 / (self.period + 1.0)
            ema = seed
            results.append(EMASnapshot(symbol, timeframe_seconds, self.period,
                                       ordered[self.period - 1].end, ema))

            for candle in ordered[self.period:]:
                ema = (candle.close * alpha) + (ema * (1.0 - alpha))
                if not isfinite(ema):
                    raise ValueError("EMA value must be finite")
                results.append(EMASnapshot(symbol, timeframe_seconds, self.period,
                                           candle.end, ema))

        return sorted(results, key=lambda item: (item.symbol, item.timeframe_seconds, item.timestamp))
