"""Stable contracts for the Mother Agent orchestration boundary."""
from dataclasses import dataclass
from enum import Enum

from core.signal.contract import SignalRecord


class ExecutionMode(str, Enum):
    """Controls whether the orchestration layer may cross into execution."""

    ANALYSIS_ONLY = "ANALYSIS_ONLY"
    SIGNAL_ONLY = "SIGNAL_ONLY"
    ASSISTIVE = "ASSISTIVE"
    AUTO_TRADING = "AUTO_TRADING"


@dataclass(frozen=True)
class OrchestrationResult:
    """One deterministic orchestration decision; no order is placed here."""

    signal: SignalRecord
    execution_allowed: bool
    reasons: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.execution_allowed and self.signal.mode == self.signal.mode.ANALYSIS_ONLY:
            raise ValueError("analysis-only mode cannot allow execution")
