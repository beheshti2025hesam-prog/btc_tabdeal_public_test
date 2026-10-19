"""Execution-cost boundary for deterministic historical backtests.

This module models explicit per-side transaction cost and adverse slippage.
It is deliberately exchange-agnostic: callers must supply assumptions and
must not treat them as venue facts unless separately sourced.
"""

from dataclasses import dataclass
import math
from typing import Iterable

from core.backtest.engine import BacktestSample
from core.strategy.baseline import BaselineDecision
from core.risk.boundary import RiskDecision


def _validate_bps(name: str, value: float) -> None:
    if not math.isfinite(value) or value < 0:
        raise ValueError(f"{name} must be finite and non-negative")


@dataclass(frozen=True)
class BacktestCostModel:
    """Per-side execution assumptions, expressed in basis points."""

    transaction_cost_bps_per_side: float = 0.0
    slippage_bps_per_side: float = 0.0

    def __post_init__(self) -> None:
        _validate_bps("transaction_cost_bps_per_side", self.transaction_cost_bps_per_side)
        _validate_bps("slippage_bps_per_side", self.slippage_bps_per_side)

    @property
    def adverse_bps_per_side(self) -> float:
        return self.transaction_cost_bps_per_side + self.slippage_bps_per_side

    def net_return(self, sample: BacktestSample) -> float:
        if sample.decision not in (BaselineDecision.LONG, BaselineDecision.SHORT):
            raise ValueError("cost model requires LONG or SHORT sample")
        if not math.isfinite(sample.entry_price) or not math.isfinite(sample.exit_price):
            raise ValueError("prices must be finite")
        if sample.entry_price <= 0 or sample.exit_price <= 0:
            raise ValueError("prices must be positive")
        direction = 1.0 if sample.decision is BaselineDecision.LONG else -1.0
        gross = direction * (sample.exit_price - sample.entry_price) / sample.entry_price
        side_cost = self.adverse_bps_per_side / 10_000.0
        return gross - (2.0 * side_cost)

    def gross_return(self, sample: BacktestSample) -> float:
        if sample.decision not in (BaselineDecision.LONG, BaselineDecision.SHORT):
            raise ValueError("cost model requires LONG or SHORT sample")
        if not math.isfinite(sample.entry_price) or not math.isfinite(sample.exit_price):
            raise ValueError("prices must be finite")
        if sample.entry_price <= 0 or sample.exit_price <= 0:
            raise ValueError("prices must be positive")
        direction = 1.0 if sample.decision is BaselineDecision.LONG else -1.0
        return direction * (sample.exit_price - sample.entry_price) / sample.entry_price


@dataclass(frozen=True)
class CostScenario:
    """Explicit measurement assumption; not an exchange-fee claim."""

    transaction_cost_bps_per_side: float
    slippage_bps_per_side: float

    def __post_init__(self) -> None:
        _validate_bps("transaction_cost_bps_per_side", self.transaction_cost_bps_per_side)
        _validate_bps("slippage_bps_per_side", self.slippage_bps_per_side)


def evaluate_samples(
    samples: Iterable[BacktestSample],
    scenarios: tuple[CostScenario, ...],
) -> tuple[tuple[CostScenario, float, int, int, int], ...]:
    if not scenarios:
        raise ValueError("at least one cost scenario is required")

    rows = tuple(samples)
    model_results = []
    for scenario in scenarios:
        model = BacktestCostModel(
            transaction_cost_bps_per_side=scenario.transaction_cost_bps_per_side,
            slippage_bps_per_side=scenario.slippage_bps_per_side,
        )
        total = 0.0
        evaluated = 0
        wins = losses = 0
        for sample in rows:
            if sample.decision is BaselineDecision.NO_TRADE or sample.risk is RiskDecision.VETO:
                continue
            value = model.net_return(sample)
            total += value
            evaluated += 1
            wins += value > 0
            losses += value < 0
        model_results.append((scenario, total, evaluated, wins, losses))
    return tuple(model_results)
