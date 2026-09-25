"""HES Trade Agent - price/VWAP relationship feature.

Feature Engine v1.0: deterministic descriptive relationship between candle
close and the matching VWAP window. No signal, strategy, risk, or execution.
"""
from dataclasses import dataclass
from datetime import timezone
from math import isfinite
from typing import Iterable, List

from core.data_engine.candles import Candle
from core.data_engine.vwap import VWAPSnapshot


@dataclass(frozen=True)
class PriceVWAPRelationship:
    symbol: str
    timeframe_seconds: int
    start: object
    end: object
    close: float
    vwap: float
    distance: float
    distance_pct: float
    relation: str


class PriceVWAPRelationshipCalculator:
    """Compare each candle close with the VWAP of the same UTC window."""

    def calculate(
        self,
        candles: Iterable[Candle],
        vwap_snapshots: Iterable[VWAPSnapshot],
    ) -> List[PriceVWAPRelationship]:
        vwap_by_window = {}
        for snapshot in vwap_snapshots:
            if not snapshot.symbol:
                raise ValueError("VWAP symbol must be non-empty")
            if snapshot.timeframe_seconds <= 0:
                raise ValueError("VWAP timeframe_seconds must be positive")
            if (
                snapshot.start.tzinfo is None
                or snapshot.start.utcoffset() is None
                or snapshot.end.tzinfo is None
                or snapshot.end.utcoffset() is None
            ):
                raise ValueError("VWAP timestamps must be timezone-aware")
            if not isfinite(snapshot.vwap):
                raise ValueError("VWAP value must be finite")
            if snapshot.vwap <= 0:
                raise ValueError("VWAP value must be positive")
            key = (
                snapshot.symbol,
                snapshot.timeframe_seconds,
                snapshot.start.astimezone(timezone.utc),
                snapshot.end.astimezone(timezone.utc),
            )
            if key in vwap_by_window:
                raise ValueError("duplicate VWAP window")
            vwap_by_window[key] = snapshot

        results: List[PriceVWAPRelationship] = []
        for candle in candles:
            if not candle.symbol:
                raise ValueError("candle symbol must be non-empty")
            if candle.timeframe_seconds <= 0:
                raise ValueError("candle timeframe_seconds must be positive")
            if (
                candle.start.tzinfo is None
                or candle.start.utcoffset() is None
                or candle.end.tzinfo is None
                or candle.end.utcoffset() is None
            ):
                raise ValueError("candle timestamps must be timezone-aware")
            if not isfinite(candle.close):
                raise ValueError("candle close must be finite")
            key = (
                candle.symbol,
                candle.timeframe_seconds,
                candle.start.astimezone(timezone.utc),
                candle.end.astimezone(timezone.utc),
            )
            snapshot = vwap_by_window.get(key)
            if snapshot is None:
                continue

            distance = candle.close - snapshot.vwap
            distance_pct = distance / snapshot.vwap
            relation = "above" if distance > 0 else "below" if distance < 0 else "at_vwap"
            results.append(
                PriceVWAPRelationship(
                    candle.symbol,
                    candle.timeframe_seconds,
                    snapshot.start.astimezone(timezone.utc),
                    snapshot.end.astimezone(timezone.utc),
                    candle.close,
                    snapshot.vwap,
                    distance,
                    distance_pct,
                    relation,
                )
            )

        return sorted(
            results,
            key=lambda item: (item.symbol, item.timeframe_seconds, item.start),
        )
