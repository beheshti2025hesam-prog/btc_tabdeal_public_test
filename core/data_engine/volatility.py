"""
Mother Agent - Volatility Intelligence
Data Intelligence v1.2

Deterministic, exchange-independent volatility primitives.
"""

from dataclasses import dataclass
from math import sqrt
from typing import Iterable, List

from core.data_engine.candles import Candle


@dataclass(frozen=True)
class VolatilitySnapshot:
    symbol: str
    timeframe_seconds: int
    candle_count: int
    mean_return: float
    return_stddev: float
    realized_volatility: float
    average_true_range: float


class VolatilityCalculator:
    """Calculate simple return-based and true-range volatility."""

    def calculate(self, candles: Iterable[Candle]) -> List[VolatilitySnapshot]:
        groups = {}
        for candle in candles:
            groups.setdefault((candle.symbol, candle.timeframe_seconds), []).append(candle)

        results = []
        for (symbol, timeframe), group in groups.items():
            ordered = sorted(group, key=lambda c: c.start)
            returns = []
            true_ranges = []

            previous_close = None
            for candle in ordered:
                if previous_close is not None and previous_close != 0:
                    returns.append((candle.close - previous_close) / previous_close)
                    true_ranges.append(
                        max(
                            candle.high - candle.low,
                            abs(candle.high - previous_close),
                            abs(candle.low - previous_close),
                        )
                    )
                previous_close = candle.close

            mean = sum(returns) / len(returns) if returns else 0.0
            variance = (
                sum((value - mean) ** 2 for value in returns) / len(returns)
                if returns else 0.0
            )
            stddev = sqrt(variance)

            results.append(
                VolatilitySnapshot(
                    symbol=symbol,
                    timeframe_seconds=timeframe,
                    candle_count=len(ordered),
                    mean_return=mean,
                    return_stddev=stddev,
                    realized_volatility=stddev * sqrt(len(returns)) if returns else 0.0,
                    average_true_range=(
                        sum(true_ranges) / len(true_ranges)
                        if true_ranges else 0.0
                    ),
                )
            )

        return sorted(results, key=lambda item: (item.symbol, item.timeframe_seconds))
