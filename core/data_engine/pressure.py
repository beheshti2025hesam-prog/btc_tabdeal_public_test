"""
HES Trade Agent - Buy/Sell Pressure.
Data Intelligence v1.0
"""
from dataclasses import dataclass
from typing import Iterable, List
from core.models.trade import CanonicalTrade

@dataclass(frozen=True)
class BuySellPressure:
    symbol: str
    buy_volume: float
    sell_volume: float
    total_volume: float
    delta: float
    buy_ratio: float
    sell_ratio: float
    buy_trade_count: int
    sell_trade_count: int

class BuySellPressureCalculator:
    def calculate(self, trades: Iterable[CanonicalTrade]) -> List[BuySellPressure]:
        groups = {}
        for trade in trades:
            groups.setdefault(trade.symbol, []).append(trade)
        results = []
        for symbol, group in groups.items():
            buy_volume=sum(t.quantity for t in group if t.side.lower()=="buy")
            sell_volume=sum(t.quantity for t in group if t.side.lower()=="sell")
            total=buy_volume+sell_volume
            results.append(BuySellPressure(symbol,buy_volume,sell_volume,total,buy_volume-sell_volume,
                                           buy_volume/total if total else 0.0,
                                           sell_volume/total if total else 0.0,
                                           sum(1 for t in group if t.side.lower()=="buy"),
                                           sum(1 for t in group if t.side.lower()=="sell")))
        return sorted(results,key=lambda item:item.symbol)
