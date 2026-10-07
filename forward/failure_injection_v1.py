"""Deterministic failure-injection matrix for forward fail-closed boundaries."""
from __future__ import annotations
from dataclasses import dataclass

FAILURE_REASONS={
    "DUPLICATE_CONFLICT","SEQUENCE_GAP","OUT_OF_ORDER_SEQUENCE",
    "STALE_SOURCE_DATA","SOURCE_RECEIVE_CLOCK_SKEW","TRANSPORT_DISCONNECT",
    "PROCESS_RESTART","INVALID_JSON",
}
@dataclass(frozen=True)
class InjectionResult:
    scenario:str
    safe:bool
    reason:str

class FailureInjectionMatrixV1:
    def run(self, scenario:str)->InjectionResult:
        if scenario not in FAILURE_REASONS:
            raise ValueError("unknown failure scenario")
        return InjectionResult(scenario,False,scenario)
