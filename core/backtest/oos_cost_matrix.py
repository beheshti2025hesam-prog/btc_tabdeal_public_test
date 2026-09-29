"""Fold-by-fold OOS execution-cost measurement boundary.

Uses the canonical execution-cost model. This layer measures explicit
assumptions only; it does not tune parameters, fit models, mutate capital,
or execute orders.
"""
from dataclasses import dataclass

from core.backtest.execution_realism import ExecutionCostConfig, ExecutionCostModel
from core.backtest.oos_protocol import OOSProtocol
from core.backtest.walk_forward import WalkForwardResult
from core.risk.boundary import RiskDecision
from core.strategy.baseline import BaselineDecision


@dataclass(frozen=True)
class OOSCostScenario:
    name: str
    config: ExecutionCostConfig


@dataclass(frozen=True)
class OOSCostMeasurement:
    fold_index: int
    scenario: OOSCostScenario
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
    scenarios: tuple[OOSCostScenario, ...],
) -> OOSCostMatrix:
    if not scenarios:
        raise ValueError("at least one cost scenario is required")
    if len(result.folds) != protocol.expected_fold_count:
        raise ValueError(
            f"protocol {protocol.protocol_id} requires "
            f"{protocol.expected_fold_count} folds, got {len(result.folds)}"
        )

    measurements: list[OOSCostMeasurement] = []
    for fold in result.folds:
        for scenario in scenarios:
            model = ExecutionCostModel(scenario.config)
            total = 0.0
            evaluated = wins = losses = 0
            for observation in fold.test:
                sample = observation.sample
                if sample.decision is BaselineDecision.NO_TRADE:
                    continue
                if sample.risk is RiskDecision.VETO:
                    continue
                direction = 1 if sample.decision is BaselineDecision.LONG else -1
                value = model.apply(
                    direction=direction,
                    entry_mid_price=sample.entry_price,
                    exit_mid_price=sample.exit_price,
                ).net_return
                total += value
                evaluated += 1
                wins += value > 0
                losses += value < 0
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

    aggregate = []
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
