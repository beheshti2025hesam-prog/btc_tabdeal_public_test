"""HES Trade Agent - deterministic swing structure feature.

Feature Engine v1.0: descriptive confirmed swing highs/lows only.
No signals, strategy, risk, execution, or order placement.
"""
from dataclasses import dataclass
from datetime import datetime, timezone
from math import isfinite
from typing import Iterable, List

from core.data_engine.candles import Candle


@dataclass(frozen=True)
class StructureSnapshot:
    symbol: str
    timeframe_seconds: int
    timestamp: datetime
    swing_high: float | None
    swing_low: float | None
    swing_high_timestamp: datetime | None
    swing_low_timestamp: datetime | None


class StructureCalculator:
    """Detect deterministic confirmed swing highs/lows from candles."""

    def __init__(self, left: int = 2, right: int = 2):
        if left <= 0 or right <= 0:
            raise ValueError("left and right must be positive")
        self.left = left
        self.right = right

    def calculate(self, candles: Iterable[Candle]) -> List[StructureSnapshot]:
        groups = {}
        for candle in candles:
            if not candle.symbol:
                raise ValueError("candle symbol must be non-empty")
            if candle.timeframe_seconds <= 0:
                raise ValueError("candle timeframe_seconds must be positive")
            if (candle.start.tzinfo is None or candle.start.utcoffset() is None or
                    candle.end.tzinfo is None or candle.end.utcoffset() is None):
                raise ValueError("candle timestamps must be timezone-aware")
            if not all(isfinite(value) for value in (candle.high, candle.low)):
                raise ValueError("candle high/low must be finite")
            if candle.high < candle.low:
                raise ValueError("candle high must be >= low")
            groups.setdefault((candle.symbol, candle.timeframe_seconds), []).append(candle)

        results = []
        for (symbol, timeframe), group in groups.items():
            ordered = sorted(group, key=lambda candle: (candle.start, candle.end))
            last_high = last_low = high_ts = low_ts = None
            for index in range(self.left, len(ordered) - self.right):
                center = ordered[index]
                neighbors = ordered[index-self.left:index] + ordered[index+1:index+self.right+1]
                if center.high >= max(c.high for c in neighbors):
                    last_high = center.high
                    high_ts = center.end.astimezone(timezone.utc)
                if center.low <= min(c.low for c in neighbors):
                    last_low = center.low
                    low_ts = center.end.astimezone(timezone.utc)
                if high_ts is not None or low_ts is not None:
                    results.append(StructureSnapshot(symbol, timeframe, center.end.astimezone(timezone.utc),
                                                      last_high, last_low, high_ts, low_ts))
        return sorted(results, key=lambda item: (item.symbol, item.timeframe_seconds, item.timestamp))
