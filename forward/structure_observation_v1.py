"""Causal, observation-only bridge from closed candles to market structure.

Applies the explicit versioned Structure Policy V1. No historical populations,
future outcomes, or strategy thresholds are introduced here.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Sequence
from .candle_normalizer_v1 import Candle15m
from .market_structure_v1 import StructureSnapshot, build_snapshot
from .structure_policy_v1 import confirm_swings_v1, label_confirmed_swings_v1, build_structure_events_v1

@dataclass(frozen=True)
class StructureObservationV1:
    observed_at: datetime
    symbol: str
    timeframe: str
    closed_candle_count: int
    status: str
    snapshot: StructureSnapshot

    def as_record(self) -> dict:
        if self.observed_at.tzinfo is None or self.observed_at.utcoffset() is None:
            raise ValueError("observed_at must be timezone-aware")
        return {
            "observed_at": self.observed_at.astimezone(timezone.utc).isoformat(),
            "symbol": self.symbol, "timeframe": self.timeframe,
            "closed_candle_count": self.closed_candle_count,
            "status": self.status, "regime": self.snapshot.regime,
            "labels": list(self.snapshot.labels),
            "events": [event.event for event in self.snapshot.events],
            "last_high": self.snapshot.last_high.price if self.snapshot.last_high else None,
            "last_low": self.snapshot.last_low.price if self.snapshot.last_low else None,
        }

def observe_closed_candles(candles: Sequence[Candle15m], *, observed_at: datetime) -> StructureObservationV1:
    if observed_at.tzinfo is None or observed_at.utcoffset() is None:
        raise ValueError("observed_at must be timezone-aware")
    observed_at = observed_at.astimezone(timezone.utc)
    ordered = sorted(candles, key=lambda candle: candle.close_time)
    symbol = ordered[0].symbol if ordered else ""
    timeframe = ordered[0].timeframe if ordered else "15m"
    for candle in ordered:
        if candle.close_time > observed_at:
            raise ValueError("closed candle occurs after observed_at")
        if candle.symbol != symbol:
            raise ValueError("mixed symbols are not allowed")
        if candle.timeframe != "15m":
            raise ValueError("only 15m candles are supported")

    if not ordered:
        snapshot = build_snapshot(observed_at=observed_at, swings=(), labels=(), events=())
        return StructureObservationV1(observed_at, symbol, timeframe, 0, "UNKNOWN_NO_CANDLES", snapshot)

    swings = confirm_swings_v1(ordered, observed_at=observed_at)
    labeled = label_confirmed_swings_v1(swings)
    labels = tuple(label for _, label in labeled if label != "UNCLASSIFIED")
    events = build_structure_events_v1(swings, observed_at=observed_at)
    snapshot = build_snapshot(observed_at=observed_at, swings=swings, labels=labels, events=events)
    status = "STRUCTURE_OBSERVED" if swings else "UNKNOWN_NO_CONFIRMED_SWINGS"
    return StructureObservationV1(observed_at, symbol, timeframe, len(ordered), status, snapshot)
