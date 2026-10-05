"""Fold-by-fold OOS execution-cost measurement boundary.

This module measures explicit cost/slippage scenarios against already-created
walk-forward test samples. It does not tune strategy parameters, fit models,
mutate capital, or execute trades.
"""

from dataclasses import dataclass

from core.backtest.costs import CostScenario, evaluate_samples
from core.backtest.oos_protocol import OOSProtocol
from core.backtest.walk_forward import WalkForwardResult


@dataclass(frozen=True)
class OOSCostMeasurement:
    fold_index: int
    scenario: CostScenario
    total_net_return: float
    evaluated: int
    wins: int
    losses: int


@dataclass(frozen=True)
class OOSCostMatrix:
    protocol_id: str
    fold_count: int
    measurements: tuple[OOSCostMeasurement, ...]
    aggregate: tuple[OOSCostMeasurement, ...]


def evaluate_oos_cost_matrix(
    result: WalkForwardResult,
    protocol: OOSProtocol,
    scenarios: tuple[CostScenario, ...],
) -> OOSCostMatrix:
    """Measure each frozen OOS fold under each explicit cost scenario."""
    if not scenarios:
        raise ValueError("at least one cost scenario is required")
    if len(result.folds) != protocol.expected_fold_count:
        raise ValueError(
            f"protocol {protocol.protocol_id} requires "
            f"{protocol.expected_fold_count} folds, got {len(result.folds)}"
        )

    measurements: list[OOSCostMeasurement] = []
    for fold in result.folds:
        results = evaluate_samples(fold.test_samples, scenarios)
        for scenario, total, evaluated, wins, losses in results:
            measurements.append(
                OOSCostMeasurement(
                    fold_index=fold.index,
                    scenario=scenario,
                    total_net_return=total,
                    evaluated=evaluated,
                    wins=wins,
                    losses=losses,
                )
            )

    aggregate: list[OOSCostMeasurement] = []
    for scenario in scenarios:
        rows = [row for row in measurements if row.scenario == scenario]
        aggregate.append(
            OOSCostMeasurement(
                fold_index=-1,
                scenario=scenario,
                total_net_return=sum(row.total_net_return for row in rows),
                evaluated=sum(row.evaluated for row in rows),
                wins=sum(row.wins for row in rows),
                losses=sum(row.losses for row in rows),
            )
        )

    return OOSCostMatrix(
        protocol_id=protocol.protocol_id,
        fold_count=len(result.folds),
        measurements=tuple(measurements),
        aggregate=tuple(aggregate),
    )
