"""Causal, observation-only bridge from closed candles to market structure.

This module does not invent swing confirmation, BOS/CHOCH, or strategy thresholds.
Until an explicit versioned structure policy exists, closed candles produce an
auditable UNKNOWN structure state.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Sequence
from .candle_normalizer_v1 import Candle15m
from .market_structure_v1 import StructureSnapshot, build_snapshot

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
    snapshot = build_snapshot(observed_at=observed_at, swings=(), labels=(), events=())
    return StructureObservationV1(
        observed_at=observed_at, symbol=symbol, timeframe=timeframe,
        closed_candle_count=len(ordered), status="UNKNOWN_NO_STRUCTURE_POLICY",
        snapshot=snapshot,
    )
