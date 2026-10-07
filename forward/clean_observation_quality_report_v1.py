"""Deterministic observation-only quality report for forward structure/regime state."""
from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class ObservationQualityReport:
    status: str
    regime: str
    quality: str
    gate_safe: bool
    report_state: str


class CleanObservationQualityReportV1:
    def build(self, *, regime: str, quality: str, gate_safe: bool) -> ObservationQualityReport:
        if regime not in {"UPTREND","DOWNTREND","TRANSITION_UNCERTAIN"}:
            raise ValueError("invalid regime")
        if quality not in {"HIGH","MEDIUM","LOW"}:
            raise ValueError("invalid quality")
        if not isinstance(gate_safe, bool):
            raise ValueError("gate_safe must be bool")
        if quality == "HIGH" and gate_safe:
            state="OBSERVATION_QUALIFIED"
        elif quality == "MEDIUM":
            state="OBSERVATION_LIMITED"
        else:
            state="OBSERVATION_UNQUALIFIED"
        return ObservationQualityReport("OBSERVATION_QUALITY_REPORT",regime,quality,gate_safe,state)
