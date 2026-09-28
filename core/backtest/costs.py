"""Execution-cost boundary for deterministic historical backtests.

This module models explicit per-side transaction cost and adverse slippage.
It is deliberately exchange-agnostic: callers must supply assumptions and
must not treat them as venue facts unless separately sourced.
"""

from dataclasses import dataclass
import math

from core.backtest.engine import BacktestSample
from core.strategy.baseline import BaselineDecision


@dataclass(frozen=True)
class BacktestCostModel:
    """Per-side execution assumptions, expressed in basis points."""

    transaction_cost_bps_per_side: float = 0.0
    slippage_bps_per_side: float = 0.0

    def __post_init__(self) -> None:
        for name, value in (
            ("transaction_cost_bps_per_side", self.transaction_cost_bps_per_side),
            ("slippage_bps_per_side", self.slippage_bps_per_side),
        ):
            if not math.isfinite(value) or value < 0:
                raise ValueError(f"{name} must be finite and non-negative")

    @property
    def adverse_bps_per_side(self) -> float:
        return (
            self.transaction_cost_bps_per_side
            + self.slippage_bps_per_side
        )

    def net_return(self, sample: BacktestSample) -> float:
        """Return one trade's direction-aware net return after costs/slippage.

        The same adverse execution assumption is applied on entry and exit.
        No capital compounding or position sizing is performed.
        """
        if sample.decision not in (BaselineDecision.LONG, BaselineDecision.SHORT):
            raise ValueError("cost model requires LONG or SHORT sample")
        if sample.entry_price <= 0 or sample.exit_price <= 0:
            raise ValueError("prices must be positive")

        direction = 1.0 if sample.decision is BaselineDecision.LONG else -1.0
        gross = direction * (sample.exit_price - sample.entry_price) / sample.entry_price
        side_cost = self.adverse_bps_per_side / 10_000.0
        return gross - (2.0 * side_cost)

    def gross_return(self, sample: BacktestSample) -> float:
        """Return the same direction-aware gross return used by BacktestEngine."""
        if sample.decision not in (BaselineDecision.LONG, BaselineDecision.SHORT):
            raise ValueError("cost model requires LONG or SHORT sample")
        if sample.entry_price <= 0 or sample.exit_price <= 0:
            raise ValueError("prices must be positive")
        direction = 1.0 if sample.decision is BaselineDecision.LONG else -1.0
        return direction * (sample.exit_price - sample.entry_price) / sample.entry_price


@dataclass(frozen=True)
class CostScenario:
    """Explicit measurement assumption; not an exchange-fee claim."""

    transaction_cost_bps_per_side: float
    slippage_bps_per_side: float


def evaluate_samples(samples, scenarios: tuple[CostScenario, ...]):
    """Return net-return measurements for each scenario over supplied samples."""
    model_results = []
    for scenario in scenarios:
        model = BacktestCostModel(
            transaction_cost_bps_per_side=scenario.transaction_cost_bps_per_side,
            slippage_bps_per_side=scenario.slippage_bps_per_side,
        )
        total = 0.0
        evaluated = 0
        wins = losses = 0
        for sample in samples:
            if sample.decision is BaselineDecision.NO_TRADE or sample.risk is RiskDecision.VETO:
                continue
            value = model.net_return(sample)
            total += value
            evaluated += 1
            wins += value > 0
            losses += value < 0
        model_results.append((scenario, total, evaluated, wins, losses))
    return tuple(model_results)
