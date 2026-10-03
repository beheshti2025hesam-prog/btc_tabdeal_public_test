"""Deterministic, execution-free backtest replay kernel.

This module evaluates supplied historical entry/exit observations. It does
not place orders, size positions, use leverage, or mutate capital.
"""
from dataclasses import dataclass
from datetime import datetime
import math
from typing import Iterable

from core.risk.boundary import RiskDecision
from core.strategy.baseline import BaselineDecision


@dataclass(frozen=True)
class BacktestSample:
    timestamp: datetime
    decision: BaselineDecision
    risk: RiskDecision
    entry_price: float
    exit_price: float


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


class BacktestEngine:
    """Replay deterministic historical observations without execution."""

    def run(self, samples: Iterable[BacktestSample]) -> BacktestResult:
        # Preserve caller order; sorting here could mask upstream chronology errors.
        rows = list(samples)
        wins = losses = evaluated = vetoed = no_trade = 0
        previous_timestamp: datetime | None = None
        total_return = 0.0

        for row in rows:
            if row.timestamp.tzinfo is None or row.timestamp.utcoffset() is None:
                raise ValueError("sample timestamp must be timezone-aware")
            if previous_timestamp is not None and row.timestamp < previous_timestamp:
                raise ValueError("backtest samples must be chronological")
            previous_timestamp = row.timestamp
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

            direction = 1.0 if row.decision is BaselineDecision.LONG else -1.0
            outcome = direction * (row.exit_price - row.entry_price) / row.entry_price
            total_return += outcome
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
        )
