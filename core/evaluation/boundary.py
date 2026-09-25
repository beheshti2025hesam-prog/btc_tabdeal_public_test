"""Deterministic, execution-free historical evaluation boundary."""
from dataclasses import dataclass
import math
from typing import Iterable

from core.risk.boundary import RiskDecision
from core.strategy.baseline import BaselineDecision


@dataclass(frozen=True)
class EvaluationMetrics:
    total: int
    long_count: int
    short_count: int
    no_trade_count: int
    risk_veto_count: int
    win_count: int
    loss_count: int
    win_rate: float


@dataclass(frozen=True)
class EvaluationResult:
    metrics: EvaluationMetrics


def evaluate_signals(
    samples: Iterable[tuple[BaselineDecision, RiskDecision, float]],
) -> EvaluationResult:
    """Evaluate completed signal outcomes without placing or simulating orders.

    Each sample is (strategy decision, risk decision, realized outcome), where
    outcome is positive for a win and negative for a loss. Zero outcomes are
    ignored for win/loss counts but remain in total.
    """
    rows = list(samples)
    total = len(rows)
    long_count = short_count = no_trade_count = risk_veto_count = 0
    win_count = loss_count = 0

    for decision, risk, outcome in rows:
        if not math.isfinite(outcome):
            raise ValueError("Outcome must be finite.")
        if decision is BaselineDecision.LONG:
            long_count += 1
        elif decision is BaselineDecision.SHORT:
            short_count += 1
        elif decision is BaselineDecision.NO_TRADE:
            no_trade_count += 1
        else:
            raise ValueError("Unknown baseline decision.")

        if risk is RiskDecision.VETO:
            risk_veto_count += 1
        elif risk is not RiskDecision.ALLOW_SIGNAL:
            raise ValueError("Unknown risk decision.")

        if risk is RiskDecision.ALLOW_SIGNAL and decision is not BaselineDecision.NO_TRADE:
            if outcome > 0:
                win_count += 1
            elif outcome < 0:
                loss_count += 1

    resolved = win_count + loss_count
    win_rate = win_count / resolved if resolved else 0.0
    return EvaluationResult(EvaluationMetrics(
        total=total,
        long_count=long_count,
        short_count=short_count,
        no_trade_count=no_trade_count,
        risk_veto_count=risk_veto_count,
        win_count=win_count,
        loss_count=loss_count,
        win_rate=win_rate,
    ))
