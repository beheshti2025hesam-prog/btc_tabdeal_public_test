"""
HES Trade Agent - Volume Intelligence.
Data Intelligence v1.0
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
    def __init__(self, spike_multiplier: float = 1.5):
        if spike_multiplier <= 0:
            raise ValueError("spike_multiplier must be positive")
        self.spike_multiplier = spike_multiplier

    def calculate(self, candles: Iterable[Candle]) -> List[VolumeSnapshot]:
        groups = {}
        for candle in candles:
            groups.setdefault((candle.symbol, candle.timeframe_seconds), []).append(candle)
        results = []
        for (symbol, timeframe), group in groups.items():
            ordered = sorted(group, key=lambda candle: candle.start)
            volumes = [c.volume for c in ordered]
            count = len(volumes)
            total = sum(volumes)
            average = total / count if count else 0.0
            variance = sum((v - average) ** 2 for v in volumes) / count if count else 0.0
            stddev = sqrt(variance)
            latest = volumes[-1] if volumes else 0.0
            ratio = latest / average if average else 0.0
            results.append(VolumeSnapshot(symbol, timeframe, count, total, average, stddev,
                                          latest, ratio, bool(average and ratio >= self.spike_multiplier)))
        return sorted(results, key=lambda item: (item.symbol, item.timeframe_seconds))
