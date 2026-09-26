"""
HES Trade Agent - Windowed Buy/Sell Pressure.
Descriptive only; no signals or execution.
"""
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable, List

from core.data_engine.window import IntelligenceWindow
from core.models.trade import CanonicalTrade


@dataclass(frozen=True)
class BuySellPressure:
    symbol: str
    timeframe_seconds: int
    window_start: datetime
    window_end: datetime
    buy_volume: float
    sell_volume: float
    total_volume: float
    delta: float
    buy_ratio: float
    sell_ratio: float
    buy_trade_count: int
    sell_trade_count: int


class BuySellPressureCalculator:
    def __init__(self, timeframe_seconds: int = 60):
        if timeframe_seconds <= 0:
            raise ValueError("timeframe_seconds must be positive")
        self.timeframe_seconds = timeframe_seconds

    def calculate(self, trades: Iterable[CanonicalTrade]) -> List[BuySellPressure]:
        groups = {}
        for trade in trades:
            timestamp = trade.timestamp.astimezone(timezone.utc)
            epoch = int(timestamp.timestamp())
            bucket = epoch - (epoch % self.timeframe_seconds)
            groups.setdefault((trade.symbol, bucket), []).append(trade)

        results = []
        for (symbol, bucket), group in groups.items():
            start = datetime.fromtimestamp(bucket, tz=timezone.utc)
            end = datetime.fromtimestamp(bucket + self.timeframe_seconds, tz=timezone.utc)
            IntelligenceWindow(symbol, self.timeframe_seconds, start, end)
            buys = [t for t in group if t.side.lower() == "buy"]
            sells = [t for t in group if t.side.lower() == "sell"]
            buy_volume = sum(t.quantity for t in buys)
            sell_volume = sum(t.quantity for t in sells)
            total = buy_volume + sell_volume
            results.append(BuySellPressure(
                symbol, self.timeframe_seconds, start, end, buy_volume, sell_volume,
                total, buy_volume - sell_volume,
                buy_volume / total if total else 0.0,
                sell_volume / total if total else 0.0,
                len(buys), len(sells),
            ))
        return sorted(results, key=lambda x: (x.symbol, x.window_start))
