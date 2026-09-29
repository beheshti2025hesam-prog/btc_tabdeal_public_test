"""Deterministic, execution-free backtest replay kernel.

This module evaluates supplied historical entry/exit observations. It does
not place orders, size positions, use leverage, or mutate capital.
"""
from dataclasses import dataclass
from datetime import datetime
import math
from typing import Iterable

from core.backtest.execution_realism import ExecutionCostModel
from core.risk.boundary import RiskDecision
from core.strategy.baseline import BaselineDecision


@dataclass(frozen=True)
class BacktestSample:
    timestamp: datetime
    decision: BaselineDecision
    risk: RiskDecision
    entry_price: float
    exit_price: float
    outcome_timestamp: datetime | None = None


@dataclass(frozen=True)
class BacktestResult:
    samples: int
    evaluated: int
    vetoed: int
    no_trade: int
    wins: int
    losses: int
    total_return: float
    win_rate: float
    compounded_return: float = 0.0


class BacktestEngine:
    """Replay deterministic historical observations without execution."""

    def __init__(self, execution_cost_model: ExecutionCostModel | None = None) -> None:
        self.execution_cost_model = execution_cost_model or ExecutionCostModel()

    def run(self, samples: Iterable[BacktestSample]) -> BacktestResult:
        rows = sorted(list(samples), key=lambda item: item.timestamp)
        wins = losses = evaluated = vetoed = no_trade = 0
        total_return = 0.0
        compounded_return = 1.0

        for row in rows:
            if row.timestamp.tzinfo is None or row.timestamp.utcoffset() is None:
                raise ValueError("sample timestamp must be timezone-aware")
            if row.outcome_timestamp is not None:
                if row.outcome_timestamp.tzinfo is None or row.outcome_timestamp.utcoffset() is None:
                    raise ValueError("outcome timestamp must be timezone-aware")
                if row.outcome_timestamp <= row.timestamp:
                    raise ValueError("outcome timestamp must be after decision timestamp")
            if not all(math.isfinite(value) for value in (row.entry_price, row.exit_price)):
                raise ValueError("prices must be finite")
            if row.entry_price <= 0 or row.exit_price <= 0:
                raise ValueError("prices must be positive")

            if row.decision is BaselineDecision.NO_TRADE:
                no_trade += 1
                continue
            if row.decision not in (BaselineDecision.LONG, BaselineDecision.SHORT):
                raise ValueError("unknown strategy decision")
            if row.risk is RiskDecision.VETO:
                vetoed += 1
                continue
            if row.risk is not RiskDecision.ALLOW_SIGNAL:
                raise ValueError("unknown risk decision")

            direction = 1 if row.decision is BaselineDecision.LONG else -1
            outcome = self.execution_cost_model.apply(
                direction=direction,
                entry_mid_price=row.entry_price,
                exit_mid_price=row.exit_price,
            ).net_return
            total_return += outcome
            compounded_return *= 1.0 + outcome
            evaluated += 1
            if outcome > 0:
                wins += 1
            elif outcome < 0:
                losses += 1

        resolved = wins + losses
        return BacktestResult(
            samples=len(rows),
            evaluated=evaluated,
            vetoed=vetoed,
            no_trade=no_trade,
            wins=wins,
            losses=losses,
            total_return=total_return,
            win_rate=wins / resolved if resolved else 0.0,
            compounded_return=compounded_return - 1.0 if evaluated else 0.0,
        )
