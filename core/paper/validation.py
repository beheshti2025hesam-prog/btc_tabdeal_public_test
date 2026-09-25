"""Execution-free paper validation over historical observations."""
from dataclasses import dataclass
from typing import Iterable

from core.backtest.validation import HistoricalObservation
from core.paper.session import PaperAction, PaperExit, PaperObservation, PaperSession, PaperState
from core.risk.boundary import RiskDecision
from core.strategy.baseline import BaselineDecision


@dataclass(frozen=True)
class PaperValidationResult:
    events: int
    entries: int
    exits: int
    holds: int
    no_trade: int
    vetoed: int
    final_state: PaperState


class PaperValidation:
    """Replay historical strategy/risk decisions as a virtual position stream.

    This layer has no P&L model and never places orders, sizes positions,
    uses leverage, mutates capital, or connects to a venue.
    """

    def run(self, observations: Iterable[HistoricalObservation]) -> PaperValidationResult:
        rows = list(observations)
        session = PaperSession()
        events: list[tuple[PaperAction, PaperState]] = []

        for row in rows:
            sample = row.sample
            if row.timestamp != sample.timestamp:
                raise ValueError("observation timestamp must match sample timestamp")

            if session.state is PaperState.LONG and (
                sample.decision is BaselineDecision.SHORT
                or sample.decision is BaselineDecision.NO_TRADE
                or sample.risk is RiskDecision.VETO
            ):
                event = session.process(
                    PaperObservation(
                        row.timestamp,
                        BaselineDecision.NO_TRADE,
                        RiskDecision.VETO,
                        sample.entry_price,
                        PaperExit.CLOSE_LONG,
                    )
                )
                events.append((event.action, event.state))
                continue

            if session.state is PaperState.SHORT and (
                sample.decision is BaselineDecision.LONG
                or sample.decision is BaselineDecision.NO_TRADE
                or sample.risk is RiskDecision.VETO
            ):
                event = session.process(
                    PaperObservation(
                        row.timestamp,
                        BaselineDecision.NO_TRADE,
                        RiskDecision.VETO,
                        sample.entry_price,
                        PaperExit.CLOSE_SHORT,
                    )
                )
                events.append((event.action, event.state))
                continue

            event = session.process(
                PaperObservation(
                    row.timestamp,
                    sample.decision,
                    sample.risk,
                    sample.entry_price,
                )
            )
            events.append((event.action, event.state))

        return PaperValidationResult(
            events=len(events),
            entries=sum(action in (PaperAction.ENTER_LONG, PaperAction.ENTER_SHORT) for action, _ in events),
            exits=sum(action in (PaperAction.CLOSE_LONG, PaperAction.CLOSE_SHORT) for action, _ in events),
            holds=sum(action in (PaperAction.HOLD_LONG, PaperAction.HOLD_SHORT) for action, _ in events),
            no_trade=sum(action is PaperAction.NO_TRADE for action, _ in events),
            vetoed=sum(action is PaperAction.VETO for action, _ in events),
            final_state=session.state,
        )
