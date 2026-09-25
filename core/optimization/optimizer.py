"""Mother Agent - deterministic zero-cost parameter optimizer v1.0.

The optimizer performs explicit candidate evaluation only. It does not use
LLMs, paid services, exchange connectivity, or hidden randomness.
"""

from dataclasses import dataclass
from typing import Callable, Iterable

from core.evaluation.metrics import EvaluationMetrics
from core.experiments.contract import ExperimentSpec
from core.experiments.runner import ExperimentResult
from core.optimization.promotion import PromotionGate


@dataclass(frozen=True)
class OptimizationCandidate:
    """A concrete experiment specification plus its evaluated metrics."""

    spec: ExperimentSpec
    metrics: EvaluationMetrics


@dataclass(frozen=True)
class OptimizationResult:
    """Deterministic accepted and rejected candidate sets."""

    candidates: tuple[OptimizationCandidate, ...]
    rejected: tuple[OptimizationCandidate, ...]


class GridSearchOptimizer:
    """Evaluate an explicit finite candidate set with no hidden state."""

    def __init__(
        self,
        evaluator: Callable[[ExperimentSpec], ExperimentResult],
        *,
        objective: str = "net_pnl",
        maximize: bool = True,
        promotion_gate: PromotionGate | None = None,
    ) -> None:
        if not objective:
            raise ValueError("objective must not be empty")
        self.evaluator = evaluator
        self.objective = objective
        self.maximize = maximize
        self.promotion_gate = promotion_gate

    def evaluate(
        self,
        specs: Iterable[ExperimentSpec],
    ) -> OptimizationResult:
        accepted: list[OptimizationCandidate] = []
        rejected: list[OptimizationCandidate] = []

        for spec in specs:
            result = self.evaluator(spec)
            metrics = result.metrics
            candidate = OptimizationCandidate(spec=spec, metrics=metrics)

            if not hasattr(metrics, self.objective):
                raise ValueError(
                    f"unknown optimization objective: {self.objective}"
                )

            value = getattr(metrics, self.objective)
            if value is None:
                raise ValueError(
                    f"optimization objective is unavailable: {self.objective}"
                )

            if self.promotion_gate is not None:
                decision = self.promotion_gate.evaluate(metrics)
                if not decision.promoted:
                    rejected.append(candidate)
                    continue

            accepted.append(candidate)

        key = lambda item: getattr(item.metrics, self.objective)
        ordered = tuple(
            sorted(
                accepted,
                key=key,
                reverse=self.maximize,
            )
        )

        return OptimizationResult(
            candidates=ordered,
            rejected=tuple(rejected),
        )
