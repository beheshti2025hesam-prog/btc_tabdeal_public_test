"""Observation-only persistence of forward regime observations."""
from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class RegimePersistence:
    status: str
    observations: int
    dominant_regime: str
    persistence_ratio: float
    stable: bool


class CleanRegimePersistenceV1:
    def observe(self, regimes: list[str]) -> RegimePersistence:
        if not regimes:
            raise ValueError("no regime observations")
        allowed={"UPTREND","DOWNTREND","TRANSITION_UNCERTAIN"}
        if any(r not in allowed for r in regimes):
            raise ValueError("invalid regime")
        counts={r:regimes.count(r) for r in allowed}
        dominant=max(counts, key=counts.get)
        ratio=counts[dominant]/len(regimes)
        stable=dominant != "TRANSITION_UNCERTAIN" and ratio == 1.0
        return RegimePersistence("REGIME_PERSISTENCE_OBSERVED",len(regimes),dominant,ratio,stable)
