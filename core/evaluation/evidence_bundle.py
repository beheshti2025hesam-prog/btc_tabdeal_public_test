"""Execution-free Evidence Bundle contract."""

from dataclasses import dataclass
from core.evaluation.producer import EvidenceResult


@dataclass(frozen=True)
class EvidenceBundle:
    source_commit: str
    results: tuple[EvidenceResult, ...]

    def __post_init__(self):
        if not isinstance(self.source_commit, str) or not self.source_commit.strip():
            raise ValueError("source_commit must be non-empty")
        if not self.results:
            raise ValueError("results must be non-empty")
        names = [r.gate_name for r in self.results]
        if any(not isinstance(r, EvidenceResult) for r in self.results):
            raise TypeError("results must contain EvidenceResult values")
        if len(names) != len(set(names)):
            raise ValueError("duplicate evidence gate")
