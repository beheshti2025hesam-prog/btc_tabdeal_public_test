"""Mother Agent - multi-timeframe feature alignment v1.0."""
from dataclasses import dataclass
from datetime import datetime
from typing import Iterable

from core.data_engine.multitimeframe import MultiTimeframeFeatures


@dataclass(frozen=True)
class AlignedFeatureSnapshot:
    symbol: str
    timestamp: datetime
    snapshots: tuple[object, ...]


class TimeframeAligner:
    """Select the latest feature snapshot at or before a target timestamp."""

    def align(
        self,
        *,
        target_timestamp: datetime,
        histories: Iterable[MultiTimeframeFeatures],
    ) -> AlignedFeatureSnapshot:
        if target_timestamp.tzinfo is None:
            raise ValueError("target_timestamp must be timezone-aware")
        selected = []
        symbol = None
        for history in histories:
            if symbol is None:
                symbol = history.symbol
            elif history.symbol != symbol:
                raise ValueError("all histories must use the same symbol")
            candidates = [s for s in history.snapshots if getattr(s, "timestamp", None) is not None
                          and s.timestamp <= target_timestamp]
            if candidates:
                selected.append(max(candidates, key=lambda s: s.timestamp))
        if symbol is None:
            raise ValueError("histories must not be empty")
        return AlignedFeatureSnapshot(symbol, target_timestamp, tuple(selected))
