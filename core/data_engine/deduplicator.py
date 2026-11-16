"""
HES Trade Agent - Trade Deduplicator.
"""
from typing import Iterable, Iterator
from core.models.trade import CanonicalTrade


class TradeDeduplicator:
    """Deduplicate only when a venue-specific event-identity capability is proven."""
    def __init__(self, *, identity_verified: bool = False) -> None:
        self.identity_verified = identity_verified

    def deduplicate(self, trades: Iterable[CanonicalTrade]) -> Iterator[CanonicalTrade]:
        if not self.identity_verified:
            # Unknown/opaque identifiers must never suppress received events.
            yield from trades
            return
        seen: set[str] = set()
        for trade in trades:
            if trade.event_id in seen:
                continue
            seen.add(trade.event_id)
            yield trade
