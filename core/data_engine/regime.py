"""
Mother Agent - Market Regime Intelligence
Data Intelligence v1.3

A transparent baseline regime classifier. It is descriptive only and does
not generate trading signals.
"""

from dataclasses import dataclass
from typing import Iterable, List

from core.data_engine.candles import Candle


@dataclass(frozen=True)
class MarketRegime:
    symbol: str
    timeframe_seconds: int
    label: str
    candle_count: int
    net_return: float
    average_range: float


class MarketRegimeClassifier:
    """
    Classify candle windows as uptrend, downtrend, range, or insufficient_data.

    Thresholds are explicit configuration rather than hidden constants.
    """

    def __init__(self, trend_threshold: float = 0.01, min_candles: int = 3):
        if trend_threshold < 0:
            raise ValueError("trend_threshold must be non-negative")
        if min_candles < 2:
            raise ValueError("min_candles must be at least 2")
        self.trend_threshold = trend_threshold
        self.min_candles = min_candles

    def classify(self, candles: Iterable[Candle]) -> List[MarketRegime]:
        groups = {}
        for candle in candles:
            groups.setdefault((candle.symbol, candle.timeframe_seconds), []).append(candle)

        results = []
        for (symbol, timeframe), group in groups.items():
            ordered = sorted(group, key=lambda c: c.start)
            if len(ordered) < self.min_candles or ordered[0].open == 0:
                label = "insufficient_data"
                net_return = 0.0
            else:
                net_return = (ordered[-1].close - ordered[0].open) / ordered[0].open
                if net_return > self.trend_threshold:
                    label = "uptrend"
                elif net_return < -self.trend_threshold:
                    label = "downtrend"
                else:
                    label = "range"

            average_range = (
                sum(c.high - c.low for c in ordered) / len(ordered)
                if ordered else 0.0
            )
            results.append(
                MarketRegime(
                    symbol=symbol,
                    timeframe_seconds=timeframe,
                    label=label,
                    candle_count=len(ordered),
                    net_return=net_return,
                    average_range=average_range,
                )
            )

        return sorted(results, key=lambda item: (item.symbol, item.timeframe_seconds))
