"""HES Trade Agent - deterministic, time-windowed VWAP Intelligence."""
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable, List

from core.models.trade import CanonicalTrade


@dataclass(frozen=True)
class VWAPSnapshot:
    symbol: str
    timeframe_seconds: int
    start: datetime
    end: datetime
    volume: float
    vwap: float
    trade_count: int


class VWAPCalculator:
    """Calculate deterministic UTC-bucketed VWAP snapshots from canonical trades."""

    def __init__(self, timeframe_seconds: int = 60):
        if timeframe_seconds <= 0:
            raise ValueError("timeframe_seconds must be positive")
        self.timeframe_seconds = timeframe_seconds

    def calculate(self, trades: Iterable[CanonicalTrade]) -> List[VWAPSnapshot]:
        groups = {}
        for trade in trades:
            if not trade.symbol:
                raise ValueError("trade symbol must be non-empty")
            if trade.timestamp.tzinfo is None or trade.timestamp.utcoffset() is None:
                raise ValueError("trade timestamp must be timezone-aware")
            timestamp = trade.timestamp.astimezone(timezone.utc)
            epoch = int(timestamp.timestamp())
            bucket_epoch = epoch - (epoch % self.timeframe_seconds)
            groups.setdefault((trade.symbol, bucket_epoch), []).append(trade)

        results: List[VWAPSnapshot] = []
        for (symbol, bucket_epoch), group in groups.items():
            ordered = sorted(group, key=lambda trade: (trade.timestamp, trade.sequence or -1))
            total_volume = sum(t.quantity for t in ordered)
            weighted_value = sum(t.price * t.quantity for t in ordered)
            start = datetime.fromtimestamp(bucket_epoch, tz=timezone.utc)
            end = datetime.fromtimestamp(
                bucket_epoch + self.timeframe_seconds, tz=timezone.utc
            )
            results.append(
                VWAPSnapshot(
                    symbol,
                    self.timeframe_seconds,
                    start,
                    end,
                    total_volume,
                    weighted_value / total_volume if total_volume else 0.0,
                    len(ordered),
                )
            )

        return sorted(results, key=lambda item: (item.symbol, item.start))
