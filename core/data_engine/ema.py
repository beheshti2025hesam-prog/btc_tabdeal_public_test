"""Mother Agent - EMA Intelligence v1.0

Deterministic exponential moving average over candle closes.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, List, Tuple

from core.data_engine.candles import Candle


@dataclass(frozen=True)
class EMAValue:
    symbol: str
    timeframe_seconds: int
    period: int
    start: datetime
    value: float


class EMACalculator:
    """Calculate EMA series per symbol/timeframe."""

    def __init__(self, period: int = 20):
        if period <= 0:
            raise ValueError("period must be positive")
        self.period = period

    def calculate(self, candles: Iterable[Candle]) -> List[EMAValue]:
        groups = {}
        for candle in candles:
            groups.setdefault(
                (candle.symbol, candle.timeframe_seconds), []
            ).append(candle)

        results: List[EMAValue] = []
        alpha = 2.0 / (self.period + 1.0)

        for (symbol, timeframe), group in groups.items():
            ordered = sorted(group, key=lambda candle: candle.start)
            if not ordered:
                continue

            ema = ordered[0].close
            results.append(
                EMAValue(
                    symbol=symbol,
                    timeframe_seconds=timeframe,
                    period=self.period,
                    start=ordered[0].start,
                    value=ema,
                )
            )

            for candle in ordered[1:]:
                ema = (candle.close * alpha) + (ema * (1.0 - alpha))
                results.append(
                    EMAValue(
                        symbol=symbol,
                        timeframe_seconds=timeframe,
                        period=self.period,
                        start=candle.start,
                        value=ema,
                    )
                )

        return sorted(
            results,
            key=lambda item: (item.symbol, item.timeframe_seconds, item.start),
        )
