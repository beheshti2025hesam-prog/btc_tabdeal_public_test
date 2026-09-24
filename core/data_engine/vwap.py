"""Mother Agent - VWAP Intelligence v1.0

Deterministic volume-weighted average price from canonical trades.
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
    """Calculate session/window VWAP per symbol."""

    def calculate(self, trades: Iterable[CanonicalTrade]) -> List[VWAPSnapshot]:
        groups = {}
        for trade in trades:
            groups.setdefault(trade.symbol, []).append(trade)

        results = []
        for symbol, group in groups.items():
            total_volume = sum(trade.quantity for trade in group)
            weighted_value = sum(trade.price * trade.quantity for trade in group)
            vwap = weighted_value / total_volume if total_volume else 0.0
            results.append(
                VWAPSnapshot(
                    symbol=symbol,
                    volume=total_volume,
                    vwap=vwap,
                    trade_count=len(group),
                )
            )

        return sorted(results, key=lambda item: item.symbol)
