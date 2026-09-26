"""
HES Trade Agent - Windowed Volume Intelligence.
Descriptive only; no signals or execution.
"""
from dataclasses import dataclass
from datetime import datetime, timezone
from math import sqrt
from typing import Iterable, List

from core.data_engine.candles import Candle
from core.data_engine.window import IntelligenceWindow


@dataclass(frozen=True)
class VolumeSnapshot:
    symbol: str
    timeframe_seconds: int
    window_start: datetime
    window_end: datetime
    candle_count: int
    total_volume: float
    average_volume: float
    volume_stddev: float
    latest_volume: float
    latest_vs_average: float
    is_volume_spike: bool


class VolumeIntelligenceCalculator:
    def __init__(self, spike_multiplier: float = 1.5, lookback: int = 20):
        if spike_multiplier <= 0:
            raise ValueError("spike_multiplier must be positive")
        if lookback <= 0:
            raise ValueError("lookback must be positive")
        self.spike_multiplier = spike_multiplier
        self.lookback = lookback

    def calculate(self, candles: Iterable[Candle]) -> List[VolumeSnapshot]:
        groups = {}
        for candle in candles:
            groups.setdefault((candle.symbol, candle.timeframe_seconds), []).append(candle)
        results = []
        for (symbol, timeframe), group in groups.items():
            ordered = sorted(group, key=lambda c: c.start)
            for index, candle in enumerate(ordered):
                history = ordered[max(0, index - self.lookback + 1):index + 1]
                volumes = [c.volume for c in history]
                average = sum(volumes) / len(volumes)
                variance = sum((v - average) ** 2 for v in volumes) / len(volumes)
                latest = candle.volume
                start = candle.start.astimezone(timezone.utc)
                end = candle.end.astimezone(timezone.utc)
                IntelligenceWindow(symbol, timeframe, start, end)
                results.append(VolumeSnapshot(
                    symbol, timeframe, start, end, len(history), sum(volumes),
                    average, sqrt(variance), latest,
                    latest / average if average else 0.0,
                    bool(average and latest / average >= self.spike_multiplier),
                ))
        return sorted(results, key=lambda x: (x.symbol, x.timeframe_seconds, x.window_start))
