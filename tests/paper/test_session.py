"""Tests for the execution-free paper-validation session."""
import unittest
from datetime import datetime, timedelta, timezone

from core.paper.session import PaperAction, PaperObservation, PaperSession, PaperState
from core.risk.boundary import RiskDecision
from core.strategy.baseline import BaselineDecision


class PaperSessionTests(unittest.TestCase):
    def test_enters_and_holds_virtual_position_without_execution(self):
        base = datetime(2026, 9, 25, tzinfo=timezone.utc)
        session = PaperSession()

        first = session.process(
            PaperObservation(base, BaselineDecision.LONG, RiskDecision.ALLOW_SIGNAL, 100.0)
        )
        second = session.process(
            PaperObservation(base + timedelta(minutes=1), BaselineDecision.LONG, RiskDecision.ALLOW_SIGNAL, 101.0)
        )

        self.assertEqual(first.action, PaperAction.ENTER_LONG)
        self.assertEqual(first.state, PaperState.LONG)
        self.assertEqual(second.action, PaperAction.HOLD_LONG)
        self.assertEqual(second.state, PaperState.LONG)

    def test_no_trade_and_veto_do_not_change_state(self):
        base = datetime(2026, 9, 25, tzinfo=timezone.utc)
        session = PaperSession()

        no_trade = session.process(
            PaperObservation(base, BaselineDecision.NO_TRADE, RiskDecision.VETO, 100.0)
        )
        veto = session.process(
            PaperObservation(base + timedelta(minutes=1), BaselineDecision.LONG, RiskDecision.VETO, 101.0)
        )

        self.assertEqual(no_trade.action, PaperAction.NO_TRADE)
        self.assertEqual(veto.action, PaperAction.VETO)
        self.assertEqual(session.state, PaperState.FLAT)

    def test_rejects_reverse_signal_without_exit_contract(self):
        base = datetime(2026, 9, 25, tzinfo=timezone.utc)
        session = PaperSession()
        session.process(PaperObservation(base, BaselineDecision.LONG, RiskDecision.ALLOW_SIGNAL, 100.0))

        with self.assertRaises(ValueError):
            session.process(
                PaperObservation(
                    base + timedelta(minutes=1),
                    BaselineDecision.SHORT,
                    RiskDecision.ALLOW_SIGNAL,
                    99.0,
                )
            )

    def test_rejects_out_of_order_observations(self):
        base = datetime(2026, 9, 25, tzinfo=timezone.utc)
        session = PaperSession()
        session.process(PaperObservation(base, BaselineDecision.NO_TRADE, RiskDecision.VETO, 100.0))

        with self.assertRaises(ValueError):
            session.process(PaperObservation(base - timedelta(seconds=1), BaselineDecision.NO_TRADE, RiskDecision.VETO, 100.0))


if __name__ == "__main__":
    unittest.main()
