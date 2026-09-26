"""
HES Trade Agent - Windowed Volatility Intelligence.
Descriptive only; no signals or execution.
"""
from dataclasses import dataclass
from datetime import datetime, timezone
from math import sqrt
from typing import Iterable, List

from core.data_engine.candles import Candle
from core.data_engine.window import IntelligenceWindow


@dataclass(frozen=True)
class VolatilitySnapshot:
    symbol: str
    timeframe_seconds: int
    window_start: datetime
    window_end: datetime
    candle_count: int
    mean_return: float
    return_stddev: float
    realized_volatility: float
    average_true_range: float


class VolatilityCalculator:
    def __init__(self, lookback: int = 20):
        if lookback <= 0:
            raise ValueError("lookback must be positive")
        self.lookback = lookback

    def calculate(self, candles: Iterable[Candle]) -> List[VolatilitySnapshot]:
        groups = {}
        for candle in candles:
            groups.setdefault((candle.symbol, candle.timeframe_seconds), []).append(candle)
        results = []
        for (symbol, timeframe), group in groups.items():
            ordered = sorted(group, key=lambda c: c.start)
            for index, candle in enumerate(ordered):
                start_index = max(0, index - self.lookback + 1)
                history = ordered[start_index:index + 1]
                returns, true_ranges = [], []
                previous_close = None if start_index == 0 else ordered[start_index - 1].close
                for current in history:
                    if previous_close is not None and previous_close != 0:
                        returns.append((current.close - previous_close) / previous_close)
                        true_ranges.append(max(
                            current.high - current.low,
                            abs(current.high - previous_close),
                            abs(current.low - previous_close),
                        ))
                    previous_close = current.close
                mean = sum(returns) / len(returns) if returns else 0.0
                variance = sum((v - mean) ** 2 for v in returns) / len(returns) if returns else 0.0
                start = candle.start.astimezone(timezone.utc)
                end = candle.end.astimezone(timezone.utc)
                IntelligenceWindow(symbol, timeframe, start, end)
                results.append(VolatilitySnapshot(
                    symbol, timeframe, start, end, len(history), mean, sqrt(variance),
                    sqrt(variance * len(returns)) if returns else 0.0,
                    sum(true_ranges) / len(true_ranges) if true_ranges else 0.0,
                ))
        return sorted(results, key=lambda x: (x.symbol, x.timeframe_seconds, x.window_start))
