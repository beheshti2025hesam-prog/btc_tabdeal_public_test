"""Execution-free paper-validation session.

This module validates signal/risk decisions as a virtual state stream. It
never places orders, sizes positions, uses leverage, mutates capital, or
connects to a venue.
"""
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from core.risk.boundary import RiskDecision
from core.strategy.baseline import BaselineDecision


class PaperState(str, Enum):
    FLAT = "FLAT"
    LONG = "LONG"
    SHORT = "SHORT"


class PaperAction(str, Enum):
    NO_TRADE = "NO_TRADE"
    VETO = "VETO"
    ENTER_LONG = "ENTER_LONG"
    ENTER_SHORT = "ENTER_SHORT"
    HOLD_LONG = "HOLD_LONG"
    HOLD_SHORT = "HOLD_SHORT"


@dataclass(frozen=True)
class PaperObservation:
    timestamp: datetime
    decision: BaselineDecision
    risk: RiskDecision
    price: float


@dataclass(frozen=True)
class PaperEvent:
    timestamp: datetime
    action: PaperAction
    state: PaperState
    price: float


class PaperSession:
    """Validate a chronological signal stream as a virtual position state."""

    def __init__(self) -> None:
        self._state = PaperState.FLAT
        self._last_timestamp: datetime | None = None

    @property
    def state(self) -> PaperState:
        return self._state

    def process(self, observation: PaperObservation) -> PaperEvent:
        timestamp = observation.timestamp
        if timestamp.tzinfo is None or timestamp.utcoffset() is None:
            raise ValueError("paper observation timestamp must be timezone-aware")
        if self._last_timestamp is not None and timestamp < self._last_timestamp:
            raise ValueError("paper observations must be chronological")
        if observation.price <= 0:
            raise ValueError("paper observation price must be positive")

        self._last_timestamp = timestamp

        if observation.decision is BaselineDecision.NO_TRADE:
            return PaperEvent(timestamp, PaperAction.NO_TRADE, self._state, observation.price)
        if observation.risk is RiskDecision.VETO:
            return PaperEvent(timestamp, PaperAction.VETO, self._state, observation.price)
        if observation.risk is not RiskDecision.ALLOW_SIGNAL:
            raise ValueError("unknown risk decision")

        if observation.decision is BaselineDecision.LONG:
            if self._state is PaperState.FLAT:
                self._state = PaperState.LONG
                action = PaperAction.ENTER_LONG
            elif self._state is PaperState.LONG:
                action = PaperAction.HOLD_LONG
            else:
                raise ValueError("opposite-direction signal requires an explicit exit contract")
        elif observation.decision is BaselineDecision.SHORT:
            if self._state is PaperState.FLAT:
                self._state = PaperState.SHORT
                action = PaperAction.ENTER_SHORT
            elif self._state is PaperState.SHORT:
                action = PaperAction.HOLD_SHORT
            else:
                raise ValueError("opposite-direction signal requires an explicit exit contract")
        else:
            raise ValueError("unknown strategy decision")

        return PaperEvent(timestamp, action, self._state, observation.price)
