"""Execution-free paper performance measurement."""
from dataclasses import dataclass
import math
from typing import Iterable

from core.backtest.validation import HistoricalObservation
from core.paper.session import PaperAction, PaperExit, PaperObservation, PaperSession, PaperState
from core.risk.boundary import RiskDecision
from core.strategy.baseline import BaselineDecision


@dataclass(frozen=True)
class PaperTrade:
    entry_timestamp: object
    exit_timestamp: object
    direction: PaperState
    entry_price: float
    exit_price: float
    return_fraction: float


@dataclass(frozen=True)
class PaperPerformanceResult:
    completed_trades: int
    wins: int
    losses: int
    flat_trades: int
    win_rate: float
    total_return: float
    max_drawdown: float
    open_state: PaperState


class PaperPerformance:
    """Measure virtual trade outcomes without capital, leverage, or execution."""

    def run(self, observations: Iterable[HistoricalObservation]) -> PaperPerformanceResult:
        session = PaperSession()
        completed: list[PaperTrade] = []
        entry_timestamp = None
        entry_price = None
        entry_state = None
        equity = 1.0
        peak = 1.0
        max_drawdown = 0.0

        for row in observations:
            sample = row.sample
            if row.timestamp != sample.timestamp:
                raise ValueError("observation timestamp must match sample timestamp")
            if not math.isfinite(sample.entry_price) or sample.entry_price <= 0:
                raise ValueError("paper performance price must be finite and positive")

            before = session.state
            exit_requested = (
                (before is PaperState.LONG and (
                    sample.decision is BaselineDecision.SHORT
                    or sample.decision is BaselineDecision.NO_TRADE
                    or sample.risk is RiskDecision.VETO
                ))
                or
                (before is PaperState.SHORT and (
                    sample.decision is BaselineDecision.LONG
                    or sample.decision is BaselineDecision.NO_TRADE
                    or sample.risk is RiskDecision.VETO
                ))
            )

            if exit_requested:
                exit_kind = PaperExit.CLOSE_LONG if before is PaperState.LONG else PaperExit.CLOSE_SHORT
                event = session.process(PaperObservation(
                    row.timestamp, BaselineDecision.NO_TRADE, RiskDecision.VETO,
                    sample.entry_price, exit_kind
                ))
                if entry_price is None or entry_state is None or entry_timestamp is None:
                    raise ValueError("paper position state missing entry provenance")
                direction = 1.0 if entry_state is PaperState.LONG else -1.0
                result = direction * (sample.entry_price - entry_price) / entry_price
                completed.append(PaperTrade(
                    entry_timestamp, row.timestamp, entry_state,
                    entry_price, sample.entry_price, result
                ))
                equity *= 1.0 + result
                peak = max(peak, equity)
                max_drawdown = max(max_drawdown, (peak - equity) / peak)
                entry_timestamp = entry_price = entry_state = None
                continue

            event = session.process(PaperObservation(
                row.timestamp, sample.decision, sample.risk, sample.entry_price
            ))
            if event.action in (PaperAction.ENTER_LONG, PaperAction.ENTER_SHORT):
                entry_timestamp = row.timestamp
                entry_price = sample.entry_price
                entry_state = event.state

        wins = sum(t.return_fraction > 0 for t in completed)
        losses = sum(t.return_fraction < 0 for t in completed)
        flat = len(completed) - wins - losses
        total_return = sum(t.return_fraction for t in completed)
        return PaperPerformanceResult(
            completed_trades=len(completed),
            wins=wins,
            losses=losses,
            flat_trades=flat,
            win_rate=wins / (wins + losses) if wins + losses else 0.0,
            total_return=total_return,
            max_drawdown=max_drawdown,
            open_state=session.state,
        )
