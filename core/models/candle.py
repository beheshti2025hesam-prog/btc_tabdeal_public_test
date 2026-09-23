from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Candle:
    timestamp: datetime
    timeframe: str
    symbol: str
    open: float
    high: float
    low: float
    close: float
    volume: float
    trade_count: int
