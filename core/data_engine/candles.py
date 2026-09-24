"""
Mother Agent - Trade to Candle Aggregator
Data Intelligence v1.0

Pure, exchange-independent trade aggregation. Raw data is never modified.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable, List

from core.models.trade import CanonicalTrade


@dataclass(frozen=True)
class Candle:
    symbol: str
    timeframe_seconds: int
    start: datetime
    end: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    trade_count: int


class TradeCandleAggregator:
    """Aggregate canonical trades into deterministic OHLCV candles."""

    def __init__(self, timeframe_seconds: int = 60):
        if timeframe_seconds <= 0:
            raise ValueError("timeframe_seconds must be positive")
        self.timeframe_seconds = timeframe_seconds

    def aggregate(self, trades: Iterable[CanonicalTrade]) -> List[Candle]:
        groups = {}
        for trade in trades:
            timestamp = trade.timestamp.astimezone(timezone.utc)
            epoch = int(timestamp.timestamp())
            bucket_epoch = epoch - (epoch % self.timeframe_seconds)
            key = (trade.symbol, bucket_epoch)
            groups.setdefault(key, []).append(trade)

        candles = []
        for (symbol, bucket_epoch), group in groups.items():
            ordered = sorted(
                group,
                key=lambda trade: (trade.timestamp, trade.sequence or -1),
            )
            start = datetime.fromtimestamp(bucket_epoch, tz=timezone.utc)
            end = datetime.fromtimestamp(
                bucket_epoch + self.timeframe_seconds,
                tz=timezone.utc,
            )
            prices = [trade.price for trade in ordered]
            candles.append(
                Candle(
                    symbol=symbol,
                    timeframe_seconds=self.timeframe_seconds,
                    start=start,
                    end=end,
                    open=prices[0],
                    high=max(prices),
                    low=min(prices),
                    close=prices[-1],
                    volume=sum(trade.quantity for trade in ordered),
                    trade_count=len(ordered),
                )
            )

        return sorted(candles, key=lambda candle: (candle.symbol, candle.start))
