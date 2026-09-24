"""Mother Agent - Deterministic evaluation metrics v1.0."""

from dataclasses import dataclass
from math import sqrt
from typing import Sequence


@dataclass(frozen=True)
class EvaluationMetrics:
    trades: int
    wins: int
    losses: int
    win_rate: float
    net_pnl: float
    profit_factor: float | None
    max_drawdown: float


class EvaluationMetricsCalculator:
    def calculate(self, pnls: Sequence[float]) -> EvaluationMetrics:
        values = list(pnls)
        wins = sum(1 for pnl in values if pnl > 0)
        losses = sum(1 for pnl in values if pnl < 0)
        gross_profit = sum(pnl for pnl in values if pnl > 0)
        gross_loss = abs(sum(pnl for pnl in values if pnl < 0))

        equity = 0.0
        peak = 0.0
        max_drawdown = 0.0
        for pnl in values:
            equity += pnl
            peak = max(peak, equity)
            max_drawdown = max(max_drawdown, peak - equity)

        return EvaluationMetrics(
            trades=len(values),
            wins=wins,
            losses=losses,
            win_rate=(wins / len(values)) if values else 0.0,
            net_pnl=sum(values),
            profit_factor=(gross_profit / gross_loss) if gross_loss else None,
            max_drawdown=max_drawdown,
        )
