"""
HES Trade Agent - Trade Deduplicator.
"""
from typing import Iterable, Iterator, Set
from core.models.trade import CanonicalTrade

class TradeDeduplicator:
    """Filter duplicate canonical events while leaving raw data untouched."""
    def deduplicate(self, trades: Iterable[CanonicalTrade]) -> Iterator[CanonicalTrade]:
        seen: Set[str] = set()
        for trade in trades:
            if trade.event_id in seen:
                continue
            seen.add(trade.event_id)
            yield trade
