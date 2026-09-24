"""Mother Agent - Volume Intelligence v1.0

Descriptive volume statistics derived from deterministic OHLCV candles.
Raw trades/candles remain read-only.
"""

from dataclasses import dataclass
from math import sqrt
from typing import Iterable, List

from core.data_engine.candles import Candle


@dataclass(frozen=True)
class VolumeSnapshot:
    symbol: str
    timeframe_seconds: int
    candle_count: int
    total_volume: float
    average_volume: float
    volume_stddev: float
    latest_volume: float
    latest_vs_average: float
    is_volume_spike: bool


class VolumeIntelligenceCalculator:
    """Calculate deterministic volume statistics per symbol/timeframe."""

    def __init__(self, spike_multiplier: float = 1.5):
        if spike_multiplier <= 0:
            raise ValueError("spike_multiplier must be positive")
        self.spike_multiplier = spike_multiplier

    def calculate(self, candles: Iterable[Candle]) -> List[VolumeSnapshot]:
        groups = {}
        for candle in candles:
            groups.setdefault(
                (candle.symbol, candle.timeframe_seconds), []
            ).append(candle)

        results = []
        for (symbol, timeframe), group in groups.items():
            ordered = sorted(group, key=lambda candle: candle.start)
            volumes = [candle.volume for candle in ordered]
            count = len(volumes)
            total = sum(volumes)
            average = total / count if count else 0.0
            variance = (
                sum((volume - average) ** 2 for volume in volumes) / count
                if count else 0.0
            )
            stddev = sqrt(variance)
            latest = volumes[-1] if volumes else 0.0
            ratio = latest / average if average else 0.0
            spike = bool(average and ratio >= self.spike_multiplier)

            results.append(
                VolumeSnapshot(
                    symbol=symbol,
                    timeframe_seconds=timeframe,
                    candle_count=count,
                    total_volume=total,
                    average_volume=average,
                    volume_stddev=stddev,
                    latest_volume=latest,
                    latest_vs_average=ratio,
                    is_volume_spike=spike,
                )
            )

        return sorted(results, key=lambda item: (item.symbol, item.timeframe_seconds))
