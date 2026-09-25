"""Stable contracts for future Mother Agent specialist agents."""
from dataclasses import dataclass
from enum import Enum
from typing import Mapping, Any


class AgentRole(str, Enum):
    DATA_QUALITY = "data_quality"
    STRUCTURE_REGIME = "structure_regime"
    SIGNAL = "signal"
    CONFIRMATION = "confirmation"
    RISK = "risk"
    DECISION = "decision"
    EXECUTION = "execution"
    EVALUATION = "evaluation"
    LEARNING = "learning"


@dataclass(frozen=True)
class AgentContext:
    symbol: str
    timeframe_seconds: int
    mode: str
    inputs: Mapping[str, Any]

    def __post_init__(self) -> None:
        if not self.symbol.strip():
            raise ValueError("symbol must not be empty")
        if self.timeframe_seconds <= 0:
            raise ValueError("timeframe_seconds must be positive")
        if not self.mode.strip():
            raise ValueError("mode must not be empty")


@dataclass(frozen=True)
class AgentResult:
    role: AgentRole
    accepted: bool
    outputs: Mapping[str, Any]
    reasons: tuple[str, ...] = ()
