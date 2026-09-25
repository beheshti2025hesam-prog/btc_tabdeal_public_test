"""Execution-free port contract for a future execution layer.

The contract is deliberately transport- and venue-agnostic. Implementations
must remain behind explicit safety controls and are not provided here.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Protocol


class ExecutionMode(str, Enum):
    DISABLED = "DISABLED"
    SHADOW = "SHADOW"


class ExecutionAction(str, Enum):
    ENTER_LONG = "ENTER_LONG"
    ENTER_SHORT = "ENTER_SHORT"
    CLOSE_LONG = "CLOSE_LONG"
    CLOSE_SHORT = "CLOSE_SHORT"


@dataclass(frozen=True)
class ExecutionRequest:
    request_id: str
    action: ExecutionAction
    symbol: str
    price: float
    mode: ExecutionMode = ExecutionMode.DISABLED


@dataclass(frozen=True)
class ExecutionResult:
    request_id: str
    accepted: bool
    reason: str


class ExecutionAdapter(Protocol):
    """Future execution port; no concrete venue implementation is included."""

    def submit(self, request: ExecutionRequest) -> ExecutionResult:
        """Accept or reject a request without defining venue mechanics."""
        ...
