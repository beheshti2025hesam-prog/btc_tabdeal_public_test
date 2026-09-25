"""Mother Agent - deterministic promotion gate v1.0.

Research-only gate. It decides whether an evaluated experiment satisfies
explicit deployment-promotion criteria. It never mutates data or executes
orders.
"""

from dataclasses import dataclass

from core.evaluation.metrics import EvaluationMetrics


@dataclass(frozen=True)
class PromotionPolicy:
    """Explicit, configurable minimum/maximum promotion criteria."""

    min_trades: int = 30
    min_win_rate: float = 0.0
    max_drawdown_pct: float | None = None
    min_expectancy: float | None = None
    require_positive_net_pnl: bool = True

    def __post_init__(self) -> None:
        if self.min_trades < 0:
            raise ValueError("min_trades must be nonnegative")
        if not 0.0 <= self.min_win_rate <= 1.0:
            raise ValueError("min_win_rate must be in [0, 1]")
        if self.max_drawdown_pct is not None and self.max_drawdown_pct < 0:
            raise ValueError("max_drawdown_pct must be nonnegative")
        if self.min_expectancy is not None:
            import math
            if not math.isfinite(self.min_expectancy):
                raise ValueError("min_expectancy must be finite")


@dataclass(frozen=True)
class PromotionDecision:
    """Deterministic promotion decision and violated criteria."""

    promoted: bool
    violations: tuple[str, ...]

    @property
    def status(self) -> str:
        return "PROMOTE" if self.promoted else "REJECT"


class PromotionGate:
    """Evaluate an experiment's metrics against an explicit policy."""

    def __init__(self, policy: PromotionPolicy | None = None):
        self.policy = policy or PromotionPolicy()

    def evaluate(self, metrics: EvaluationMetrics) -> PromotionDecision:
        violations: list[str] = []

        if metrics.trades < self.policy.min_trades:
            violations.append("min_trades")

        if metrics.win_rate < self.policy.min_win_rate:
            violations.append("min_win_rate")

        if (
            self.policy.max_drawdown_pct is not None
            and metrics.max_drawdown_pct > self.policy.max_drawdown_pct
        ):
            violations.append("max_drawdown_pct")

        if (
            self.policy.min_expectancy is not None
            and metrics.expectancy < self.policy.min_expectancy
        ):
            violations.append("min_expectancy")

        if self.policy.require_positive_net_pnl and metrics.net_pnl <= 0:
            violations.append("positive_net_pnl")

        return PromotionDecision(
            promoted=not violations,
            violations=tuple(violations),
        )
