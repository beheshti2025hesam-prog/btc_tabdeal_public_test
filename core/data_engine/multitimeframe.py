"""Mother Agent - Multi-Timeframe Feature Alignment v1.0

Aligns already-computed feature snapshots without generating signals.
"""

from dataclasses import dataclass
from typing import Sequence

from core.data_engine.feature_engine import FeatureSnapshot


@dataclass(frozen=True)
class MultiTimeframeFeatures:
    symbol: str
    snapshots: tuple[FeatureSnapshot, ...]

    @property
    def timeframes(self) -> tuple[int, ...]:
        return tuple(snapshot.timeframe_seconds for snapshot in self.snapshots)


class MultiTimeframeFeatureEngine:
    """Deterministically validate and align snapshots by timeframe."""

    def build(
        self,
        snapshots: Sequence[FeatureSnapshot],
    ) -> MultiTimeframeFeatures:
        if not snapshots:
            raise ValueError("at least one feature snapshot is required")

        symbol = snapshots[0].symbol
        seen: set[int] = set()

        for snapshot in snapshots:
            if snapshot.symbol != symbol:
                raise ValueError("all snapshots must use the same symbol")
            if snapshot.timeframe_seconds <= 0:
                raise ValueError("timeframe must be positive")
            if snapshot.timeframe_seconds in seen:
                raise ValueError("duplicate timeframe")
            seen.add(snapshot.timeframe_seconds)

        ordered = tuple(sorted(snapshots, key=lambda item: item.timeframe_seconds))
        return MultiTimeframeFeatures(symbol=symbol, snapshots=ordered)
