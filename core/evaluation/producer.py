"""Execution-free evidence producer contract.

An evidence producer converts validated evaluation context into one immutable
gate result. It does not choose thresholds, rank strategies, promote builds,
or execute trades.
"""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class EvidenceResult:
    """Immutable evidence produced for one named gate."""

    gate_name: str
    passed: bool
    details: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.gate_name, str) or not self.gate_name.strip():
            raise ValueError("Evidence result gate_name must be non-empty.")
        if not isinstance(self.passed, bool):
            raise ValueError("Evidence result passed must be bool.")
        if not isinstance(self.details, str):
            raise ValueError("Evidence result details must be str.")


class EvidenceProducer(Protocol):
    """Structural protocol for deterministic evidence producers."""

    @property
    def gate_name(self) -> str:
        """Return the stable name of the gate this producer supplies."""

    def produce(self, context: object) -> EvidenceResult:
        """Produce immutable evidence from supplied evaluation context."""
