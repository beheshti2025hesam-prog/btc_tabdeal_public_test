"""Causal forward-only regime snapshot derived from confirmed structure labels/events."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal, Sequence
from .market_structure_v1 import Regime, StructureEvent, StructureLabel

@dataclass(frozen=True)
class RegimeSnapshotV1:
    observed_at: datetime
    regime: Regime
    confidence_state: Literal["KNOWN","UNKNOWN"]
    source_labels: tuple[StructureLabel,...]
    source_event: str | None
    reason: str

    def as_record(self) -> dict:
        return {
            "observed_at": self.observed_at.astimezone(timezone.utc).isoformat(),
            "regime": self.regime,
            "confidence_state": self.confidence_state,
            "source_labels": list(self.source_labels),
            "source_event": self.source_event,
            "reason": self.reason,
        }

def infer_regime_v1(labels: Sequence[StructureLabel]) -> Regime:
    x=tuple(labels)
    if len(x)<2: return "UNKNOWN"
    recent=x[-4:]
    if "HH" in recent and "HL" in recent and "LL" not in recent and recent[-1] != "LL":
        return "UPTREND"
    if "LL" in recent and "LH" in recent and "HH" not in recent and recent[-1] != "HH":
        return "DOWNTREND"
    if ("HH" in recent and "LL" in recent) or len(set(recent))==1:
        return "RANGE"
    return "UNKNOWN"

def build_regime_snapshot_v1(*, observed_at: datetime, labels: Sequence[StructureLabel], events: Sequence[StructureEvent]=()) -> RegimeSnapshotV1:
    if observed_at.tzinfo is None or observed_at.utcoffset() is None:
        raise ValueError("observed_at must be timezone-aware")
    observed_at=observed_at.astimezone(timezone.utc)
    for e in events:
        if e.observed_at > observed_at or e.reference_candle_time > observed_at:
            raise ValueError("structure event occurs after observed_at")
    regime=infer_regime_v1(labels)
    latest=events[-1].event if events else None
    return RegimeSnapshotV1(observed_at,regime,"KNOWN" if regime!="UNKNOWN" else "UNKNOWN",tuple(labels),latest,"CONFIRMED_STRUCTURE_LABELS")
