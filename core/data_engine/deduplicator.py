"""
Mother Agent - Trade Deduplicator
Data Engine v1.0
"""

from typing import Iterable, Iterator, Set

from core.models.trade import CanonicalTrade


class TradeDeduplicator:
    """
    Removes duplicate CanonicalTrade events.

    Deduplication is based on the deterministic event_id.

    This component does not modify Raw Data.
    It only filters the CanonicalTrade stream.
    """

    def deduplicate(
        self,
        trades: Iterable[CanonicalTrade],
    ) -> Iterator[CanonicalTrade]:
        """
        Yield each unique trade only once.

        The first occurrence of each event_id is preserved.
        """

        seen_event_ids: Set[str] = set()

        for trade in trades:
            if trade.event_id in seen_event_ids:
                continue

            seen_event_ids.add(trade.event_id)

            yield trade
