"""Deterministic long-horizon health/soak harness; no network or execution."""
from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True)
class SoakSummary:
    samples: int
    failures: int
    safe: bool

class ForwardSoakHarnessV1:
    def __init__(self) -> None:
        self.samples=0
        self.failures=0

    def record(self, *, healthy: bool) -> None:
        self.samples += 1
        if not healthy:
            self.failures += 1

    def summary(self) -> SoakSummary:
        return SoakSummary(self.samples,self.failures,self.samples > 0 and self.failures == 0)

    def reset(self) -> None:
        self.samples=0
        self.failures=0
