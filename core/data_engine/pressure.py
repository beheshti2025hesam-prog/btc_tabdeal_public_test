"""
Mother Agent - Buy/Sell Pressure
Data Intelligence v1.1

Derives directional trade-volume pressure from canonical trades.
Raw data is read-only and no exchange-specific assumptions are required
beyond normalized side values.
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
    """Calculate deterministic buy/sell volume pressure."""

    def calculate(self, trades: Iterable[CanonicalTrade]) -> List[BuySellPressure]:
        groups = {}
        for trade in trades:
            groups.setdefault(trade.symbol, []).append(trade)

        results = []
        for symbol, group in groups.items():
            buy_volume = sum(
                trade.quantity for trade in group if trade.side.lower() == "buy"
            )
            sell_volume = sum(
                trade.quantity for trade in group if trade.side.lower() == "sell"
            )
            total_volume = buy_volume + sell_volume
            results.append(
                BuySellPressure(
                    symbol=symbol,
                    buy_volume=buy_volume,
                    sell_volume=sell_volume,
                    total_volume=total_volume,
                    delta=buy_volume - sell_volume,
                    buy_ratio=(buy_volume / total_volume) if total_volume else 0.0,
                    sell_ratio=(sell_volume / total_volume) if total_volume else 0.0,
                    buy_trade_count=sum(
                        1 for trade in group if trade.side.lower() == "buy"
                    ),
                    sell_trade_count=sum(
                        1 for trade in group if trade.side.lower() == "sell"
                    ),
                )
            )

        return sorted(results, key=lambda item: item.symbol)
