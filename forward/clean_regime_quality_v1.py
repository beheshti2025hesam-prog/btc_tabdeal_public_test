"""Observation-only quality classification for forward regime state."""
from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class RegimeQuality:
    status: str
    regime: str
    quality: str
    reason: str


class CleanRegimeQualityV1:
    def observe(self, *, regime: str, persistence_ratio: float, transition: str) -> RegimeQuality:
        if regime not in {"UPTREND","DOWNTREND","TRANSITION_UNCERTAIN"}:
            raise ValueError("invalid regime")
        if not 0.0 <= float(persistence_ratio) <= 1.0:
            raise ValueError("invalid persistence ratio")
        if not isinstance(transition, str) or not transition:
            raise ValueError("transition required")
        if regime == "TRANSITION_UNCERTAIN":
            return RegimeQuality("REGIME_QUALITY_OBSERVED",regime,"LOW","TRANSITION_UNCERTAIN")
        if persistence_ratio < 1.0:
            return RegimeQuality("REGIME_QUALITY_OBSERVED",regime,"MEDIUM","REGIME_NOT_FULLY_PERSISTENT")
        if transition not in {"NO_CHANGE","EXITED_UNCERTAIN"}:
            return RegimeQuality("REGIME_QUALITY_OBSERVED",regime,"MEDIUM","RECENT_REGIME_TRANSITION")
        return RegimeQuality("REGIME_QUALITY_OBSERVED",regime,"HIGH","STABLE_AND_PERSISTENT")
