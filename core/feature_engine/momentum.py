"""HES Trade Agent - deterministic price momentum feature.

Feature Engine v1.0: descriptive close-to-close momentum only.
No signals, strategy, risk, execution, or order placement.
"""
from dataclasses import dataclass
from datetime import datetime, timezone
from math import isfinite
from typing import Iterable, List

from core.data_engine.candles import Candle


@dataclass(frozen=True)
class MomentumSnapshot:
    symbol: str
    timeframe_seconds: int
    period: int
    timestamp: datetime
    value: float
    value_pct: float


class MomentumCalculator:
    """Calculate deterministic close-to-close momentum snapshots."""

    def __init__(self, period: int = 10):
        if period <= 0:
            raise ValueError("period must be positive")
        self.period = period

    def calculate(self, candles: Iterable[Candle]) -> List[MomentumSnapshot]:
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

        results: List[MomentumSnapshot] = []
        for (symbol, timeframe_seconds), group in groups.items():
            ordered = sorted(group, key=lambda candle: (candle.start, candle.end))
            if len(ordered) <= self.period:
                continue

            for index in range(self.period, len(ordered)):
                current = ordered[index].close
                previous = ordered[index - self.period].close
                if previous == 0.0:
                    raise ValueError("momentum reference close must be non-zero")
                value = current - previous
                value_pct = (value / previous) * 100.0
                if not isfinite(value) or not isfinite(value_pct):
                    raise ValueError("momentum values must be finite")
                results.append(
                    MomentumSnapshot(
                        symbol,
                        timeframe_seconds,
                        self.period,
                        ordered[index].end.astimezone(timezone.utc),
                        value,
                        value_pct,
                    )
                )

        return sorted(results, key=lambda item: (item.symbol, item.timeframe_seconds, item.timestamp))
