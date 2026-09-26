"""
HES Trade Agent - Windowed Market Regime Intelligence.
Descriptive only; no signals or execution.
"""
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable, List

from core.data_engine.candles import Candle
from core.data_engine.window import IntelligenceWindow


@dataclass(frozen=True)
class MarketRegime:
    symbol: str
    timeframe_seconds: int
    window_start: datetime
    window_end: datetime
    label: str
    candle_count: int
    net_return: float
    average_range: float


class MarketRegimeClassifier:
    def __init__(self, trend_threshold: float = 0.01, min_candles: int = 3, lookback: int = 20):
        if trend_threshold < 0:
            raise ValueError("trend_threshold must be non-negative")
        if min_candles < 2:
            raise ValueError("min_candles must be at least 2")
        if lookback <= 0:
            raise ValueError("lookback must be positive")
        self.trend_threshold = trend_threshold
        self.min_candles = min_candles
        self.lookback = lookback

    def classify(self, candles: Iterable[Candle]) -> List[MarketRegime]:
        groups = {}
        for candle in candles:
            groups.setdefault((candle.symbol, candle.timeframe_seconds), []).append(candle)
        results = []
        for (symbol, timeframe), group in groups.items():
            ordered = sorted(group, key=lambda c: c.start)
            for index, candle in enumerate(ordered):
                history = ordered[max(0, index - self.lookback + 1):index + 1]
                start = candle.start.astimezone(timezone.utc)
                end = candle.end.astimezone(timezone.utc)
                IntelligenceWindow(symbol, timeframe, start, end)
                if len(history) < self.min_candles or history[0].open == 0:
                    label, net_return = "insufficient_data", 0.0
                else:
                    net_return = (history[-1].close - history[0].open) / history[0].open
                    label = ("uptrend" if net_return >= self.trend_threshold
                             else "downtrend" if net_return <= -self.trend_threshold
                             else "range")
                average_range = sum(c.high - c.low for c in history) / len(history)
                results.append(MarketRegime(
                    symbol, timeframe, start, end, label, len(history),
                    net_return, average_range,
                ))
        return sorted(results, key=lambda x: (x.symbol, x.timeframe_seconds, x.window_start))
