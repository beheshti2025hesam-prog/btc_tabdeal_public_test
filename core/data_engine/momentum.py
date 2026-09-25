"""Mother Agent - Momentum Intelligence v1.0

Deterministic descriptive momentum metrics from candle closes.
No trading decisions are produced.
"""

from dataclasses import dataclass
from typing import Iterable, List
from core.data_engine.candles import Candle


@dataclass(frozen=True)
class MomentumSnapshot:
    symbol: str
    timeframe_seconds: int
    candle_count: int
    latest_return: float
    momentum_return: float
    average_return: float
    positive_candles: int
    negative_candles: int


class MomentumCalculator:
    def __init__(self, lookback: int = 5):
        if lookback <= 0:
            raise ValueError("lookback must be positive")
        self.lookback = lookback

    def calculate(self, candles: Iterable[Candle]) -> List[MomentumSnapshot]:
        groups = {}
        for candle in candles:
            groups.setdefault((candle.symbol, candle.timeframe_seconds), []).append(candle)

        results = []
        for (symbol, timeframe), group in groups.items():
            ordered = sorted(group, key=lambda c: c.start)
            closes = [c.close for c in ordered]
            returns = [
                (closes[i] / closes[i - 1]) - 1.0
                for i in range(1, len(closes))
                if closes[i - 1] != 0
            ]
            window = returns[-self.lookback:]
            momentum = 0.0
            if window:
                growth = 1.0
                for r in window:
                    growth *= 1.0 + r
                momentum = growth - 1.0
            results.append(MomentumSnapshot(
                symbol=symbol,
                timeframe_seconds=timeframe,
                candle_count=len(ordered),
                latest_return=returns[-1] if returns else 0.0,
                momentum_return=momentum,
                average_return=sum(window) / len(window) if window else 0.0,
                positive_candles=sum(1 for r in window if r > 0),
                negative_candles=sum(1 for r in window if r < 0),
            ))
        return sorted(results, key=lambda x: (x.symbol, x.timeframe_seconds))
