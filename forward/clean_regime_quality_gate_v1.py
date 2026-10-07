"""Observation-only gate for regime quality state."""
from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class RegimeQualityGate:
    status: str
    safe_for_observation: bool
    reason: str


class CleanRegimeQualityGateV1:
    def evaluate(self, quality: str) -> RegimeQualityGate:
        if quality not in {"HIGH","MEDIUM","LOW"}:
            raise ValueError("invalid regime quality")
        if quality == "HIGH":
            return RegimeQualityGate("REGIME_QUALITY_GATE_OBSERVED",True,"HIGH_QUALITY_STRUCTURE")
        if quality == "MEDIUM":
            return RegimeQualityGate("REGIME_QUALITY_GATE_OBSERVED",False,"MEDIUM_QUALITY_NOT_PROMOTED")
        return RegimeQualityGate("REGIME_QUALITY_GATE_OBSERVED",False,"LOW_QUALITY_NOT_PROMOTED")
