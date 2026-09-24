"""Mother Agent - Support / Resistance Intelligence v1.0

Deterministic descriptive levels from candle pivots.
No trading signals are generated here.
"""

from dataclasses import dataclass
from typing import Iterable, List

from core.data_engine.candles import Candle


@dataclass(frozen=True)
class PriceLevel:
    symbol: str
    timeframe_seconds: int
    kind: str
    price: float
    touches: int


class SupportResistanceCalculator:
    """Detect local pivot levels and cluster nearby prices."""

    def __init__(self, tolerance: float = 0.002, min_touches: int = 1):
        if tolerance < 0:
            raise ValueError("tolerance must be non-negative")
        if min_touches <= 0:
            raise ValueError("min_touches must be positive")
        self.tolerance = tolerance
        self.min_touches = min_touches

    def calculate(self, candles: Iterable[Candle]) -> List[PriceLevel]:
        groups = {}
        for candle in candles:
            groups.setdefault(
                (candle.symbol, candle.timeframe_seconds), []
            ).append(candle)

        results = []
        for (symbol, timeframe), group in groups.items():
            ordered = sorted(group, key=lambda candle: candle.start)
            supports = []
            resistances = []

            for i in range(1, len(ordered) - 1):
                prev_candle, candle, next_candle = ordered[i - 1:i + 2]
                if candle.low <= prev_candle.low and candle.low <= next_candle.low:
                    supports.append(candle.low)
                if candle.high >= prev_candle.high and candle.high >= next_candle.high:
                    resistances.append(candle.high)

            for kind, prices in (("support", supports), ("resistance", resistances)):
                for cluster in self._cluster(prices):
                    if len(cluster) >= self.min_touches:
                        results.append(
                            PriceLevel(
                                symbol=symbol,
                                timeframe_seconds=timeframe,
                                kind=kind,
                                price=sum(cluster) / len(cluster),
                                touches=len(cluster),
                            )
                        )

        return sorted(
            results,
            key=lambda item: (item.symbol, item.timeframe_seconds, item.kind, item.price),
        )

    def _cluster(self, prices: List[float]) -> List[List[float]]:
        clusters: List[List[float]] = []
        for price in sorted(prices):
            placed = False
            for cluster in clusters:
                center = sum(cluster) / len(cluster)
                if center == 0 or abs(price - center) / abs(center) <= self.tolerance:
                    cluster.append(price)
                    placed = True
                    break
            if not placed:
                clusters.append([price])
        return clusters
