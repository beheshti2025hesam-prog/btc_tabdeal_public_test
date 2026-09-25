"""
HES Trade Agent - VWAP Intelligence.
Data Intelligence v1.0
"""
from dataclasses import dataclass
from typing import Iterable, List
from core.models.trade import CanonicalTrade

@dataclass(frozen=True)
class VWAPSnapshot:
    symbol: str
    volume: float
    vwap: float
    trade_count: int

class VWAPCalculator:
    def calculate(self, trades: Iterable[CanonicalTrade]) -> List[VWAPSnapshot]:
        groups = {}
        for trade in trades:
            groups.setdefault(trade.symbol, []).append(trade)
        results = []
        for symbol, group in groups.items():
            total_volume = sum(t.quantity for t in group)
            weighted_value = sum(t.price * t.quantity for t in group)
            results.append(VWAPSnapshot(symbol, total_volume,
                                        weighted_value / total_volume if total_volume else 0.0,
                                        len(group)))
        return sorted(results, key=lambda item: item.symbol)
