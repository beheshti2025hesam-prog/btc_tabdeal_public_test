"""Mother Agent - Market Structure Intelligence v1.0

Deterministic swing structure descriptors. This is descriptive only:
no entries, exits, or trade signals.
"""

from dataclasses import dataclass
from typing import Iterable, List

from core.data_engine.candles import Candle


@dataclass(frozen=True)
class StructureSnapshot:
    symbol: str
    timeframe_seconds: int
    swing_high: float | None
    swing_low: float | None
    structure: str
    candle_count: int


class MarketStructureCalculator:
    def calculate(self, candles: Iterable[Candle]) -> List[StructureSnapshot]:
        groups = {}
        for candle in candles:
            groups.setdefault((candle.symbol, candle.timeframe_seconds), []).append(candle)

        results = []
        for (symbol, timeframe), group in groups.items():
            ordered = sorted(group, key=lambda c: c.start)
            highs = [c.high for c in ordered]
            lows = [c.low for c in ordered]
            swing_high = max(highs) if highs else None
            swing_low = min(lows) if lows else None

            structure = "insufficient_data"
            if len(ordered) >= 4:
                mid = len(ordered) // 2
                first = ordered[:mid]
                second = ordered[mid:]
                first_high, second_high = max(c.high for c in first), max(c.high for c in second)
                first_low, second_low = min(c.low for c in first), min(c.low for c in second)
                if second_high > first_high and second_low > first_low:
                    structure = "higher_high_higher_low"
                elif second_high < first_high and second_low < first_low:
                    structure = "lower_high_lower_low"
                else:
                    structure = "mixed"

            results.append(StructureSnapshot(
                symbol, timeframe, swing_high, swing_low, structure, len(ordered)
            ))
        return sorted(results, key=lambda x: (x.symbol, x.timeframe_seconds))
