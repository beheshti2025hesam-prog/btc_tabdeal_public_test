"""HES Trade Agent - deterministic support/resistance feature.

Feature Engine v1.0: descriptive price levels derived from candles only.
No signals, strategy, risk, execution, or order placement.
"""
from dataclasses import dataclass
from datetime import datetime, timezone
from math import isfinite
from typing import Iterable, List


@dataclass(frozen=True)
class SupportResistanceSnapshot:
    symbol: str
    timeframe_seconds: int
    timestamp: datetime
    support: float
    resistance: float
    lookback: int


class SupportResistanceCalculator:
    """Calculate deterministic rolling support/resistance from candle extremes."""

    def __init__(self, lookback: int = 20):
        if lookback <= 0:
            raise ValueError("lookback must be positive")
        self.lookback = lookback

    def calculate(self, candles: Iterable[object]) -> List[SupportResistanceSnapshot]:
        groups = {}
        for candle in candles:
            if not candle.symbol:
                raise ValueError("candle symbol must be non-empty")
            if candle.timeframe_seconds <= 0:
                raise ValueError("candle timeframe_seconds must be positive")
            if (
                candle.start.tzinfo is None
                or candle.start.utcoffset() is None
                or candle.end.tzinfo is None
                or candle.end.utcoffset() is None
            ):
                raise ValueError("candle timestamps must be timezone-aware")
            if not all(isfinite(value) for value in (candle.high, candle.low)):
                raise ValueError("candle high/low must be finite")
            if candle.high < candle.low:
                raise ValueError("candle high must be >= low")
            groups.setdefault((candle.symbol, candle.timeframe_seconds), []).append(candle)

        results = []
        for (symbol, timeframe), group in groups.items():
            ordered = sorted(group, key=lambda candle: (candle.start, candle.end))
            for index in range(self.lookback - 1, len(ordered)):
                window = ordered[index - self.lookback + 1:index + 1]
                support = min(candle.low for candle in window)
                resistance = max(candle.high for candle in window)
                results.append(
                    SupportResistanceSnapshot(
                        symbol,
                        timeframe,
                        ordered[index].end.astimezone(timezone.utc),
                        support,
                        resistance,
                        self.lookback,
                    )
                )
        return sorted(results, key=lambda item: (item.symbol, item.timeframe_seconds, item.timestamp))
