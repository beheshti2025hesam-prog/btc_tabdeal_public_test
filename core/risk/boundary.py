"""Deterministic capital/risk boundary.

Signal-only safety layer. It can veto a strategy decision, but it never
executes orders, sizes positions, sets leverage, or mutates capital.
"""
from dataclasses import dataclass
from enum import Enum
import math

from core.strategy.baseline import BaselineDecision


class RiskDecision(str, Enum):
    ALLOW_SIGNAL = "ALLOW_SIGNAL"
    VETO = "VETO"


@dataclass(frozen=True)
class RiskInput:
    decision: BaselineDecision
    equity: float
    risk_fraction: float = 0.01
    max_drawdown_fraction: float = 0.20
    current_drawdown_fraction: float = 0.0
    leverage: float = 1.0


class RiskPolicy:
    """Conservative pre-execution veto policy."""

    def evaluate(self, data: RiskInput) -> RiskDecision:
        if data.decision is BaselineDecision.NO_TRADE:
            return RiskDecision.VETO

        values = (
            data.equity,
            data.risk_fraction,
            data.max_drawdown_fraction,
            data.current_drawdown_fraction,
            data.leverage,
        )
        if not all(math.isfinite(value) for value in values):
            return RiskDecision.VETO

        if data.equity <= 0:
            return RiskDecision.VETO
        if not 0 < data.risk_fraction <= 0.02:
            return RiskDecision.VETO
        if not 0 < data.max_drawdown_fraction < 1:
            return RiskDecision.VETO
        if not 0 <= data.current_drawdown_fraction < 1:
            return RiskDecision.VETO
        if data.current_drawdown_fraction >= data.max_drawdown_fraction:
            return RiskDecision.VETO
        if data.leverage < 1 or data.leverage > 1:
            return RiskDecision.VETO

        return RiskDecision.ALLOW_SIGNAL
