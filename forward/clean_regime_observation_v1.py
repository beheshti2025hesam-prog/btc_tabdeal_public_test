"""Observation-only regime classification from forward structure stability."""
from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class RegimeObservation:
    status: str
    regime: str
    confidence_state: str


class CleanRegimeObservationV1:
    def observe(self, stable_bias: str) -> RegimeObservation:
        if stable_bias == "UP_STABLE":
            return RegimeObservation("REGIME_OBSERVED", "UPTREND", "STRUCTURE_ALIGNED")
        if stable_bias == "DOWN_STABLE":
            return RegimeObservation("REGIME_OBSERVED", "DOWNTREND", "STRUCTURE_ALIGNED")
        if stable_bias == "UNSTABLE":
            return RegimeObservation("REGIME_OBSERVED", "TRANSITION_UNCERTAIN", "STRUCTURE_MIXED")
        raise ValueError("invalid stability state")
