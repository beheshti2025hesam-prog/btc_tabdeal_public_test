"""Forward-only market structure measurement primitives.

This module intentionally does not generate trading signals.
It exposes deterministic swing/structure records from already normalized
15-minute candles. Any production swing confirmation policy must be supplied
explicitly as a versioned policy; this reference layer does not invent one.
"""

from __future__ import annotations
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal, Sequence
from .candle_normalizer_v1 import Candle15m

Regime = Literal["UPTREND","DOWNTREND","RANGE","UNKNOWN"]
StructureLabel = Literal["HH","HL","LH","LL"]

@dataclass(frozen=True)
class SwingPoint:
    kind: Literal["SWING_HIGH","SWING_LOW"]
    price: Decimal
    candle_time: object
    sequence: int

@dataclass(frozen=True)
class StructureEvent:
    event: StructureLabel | Literal["BOS","CHOCH"]
    direction: Literal["BULLISH","BEARISH","NONE"]
    observed_at: object
    reference_candle_time: object
    reference_price: Decimal
    reason: str

@dataclass(frozen=True)
class StructureSnapshot:
    observed_at: object
    regime: Regime
    last_high: SwingPoint | None
    last_low: SwingPoint | None
    labels: tuple[StructureLabel, ...]
    events: tuple[StructureEvent, ...]

def classify_swing_labels(previous: Sequence[SwingPoint], current: SwingPoint) -> tuple[StructureLabel, ...]:
    same = [x for x in previous if x.kind == current.kind]
    if not same:
        return ()
    prior = same[-1]
    if current.kind == "SWING_HIGH":
        return ("HH",) if current.price > prior.price else ("LH",)
    return ("HL",) if current.price > prior.price else ("LL",)

def infer_regime(labels: Sequence[StructureLabel]) -> Regime:
    labels = tuple(labels)
    if len(labels) < 2:
        return "UNKNOWN"
    recent = labels[-4:]
    if "HH" in recent and "HL" in recent and "LL" not in recent:
        return "UPTREND"
    if "LL" in recent and "LH" in recent and "HH" not in recent:
        return "DOWNTREND"
    if ("HH" in recent and "LL" in recent) or len(set(recent)) == 1:
        return "RANGE"
    return "UNKNOWN"

def build_snapshot(
    observed_at,
    swings: Sequence[SwingPoint],
    labels: Sequence[StructureLabel],
    events: Sequence[StructureEvent],
) -> StructureSnapshot:
    highs = [x for x in swings if x.kind == "SWING_HIGH"]
    lows = [x for x in swings if x.kind == "SWING_LOW"]
    return StructureSnapshot(
        observed_at=observed_at,
        regime=infer_regime(labels),
        last_high=highs[-1] if highs else None,
        last_low=lows[-1] if lows else None,
        labels=tuple(labels),
        events=tuple(events),
    )
