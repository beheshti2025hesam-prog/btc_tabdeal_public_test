"""Tests for execution-free paper validation over historical observations."""
import unittest
from datetime import datetime, timedelta, timezone

from core.backtest.engine import BacktestSample
from core.backtest.validation import HistoricalObservation
from core.paper.session import PaperState
from core.paper.validation import PaperValidation
from core.risk.boundary import RiskDecision
from core.strategy.baseline import BaselineDecision


class PaperValidationTests(unittest.TestCase):
    def _row(self, minute, decision, risk=RiskDecision.ALLOW_SIGNAL, price=100.0):
        timestamp = datetime(2026, 9, 25, 0, minute, tzinfo=timezone.utc)
        sample = BacktestSample(timestamp, decision, risk, price, price)
        return HistoricalObservation(timestamp, sample)

    def test_replays_entry_hold_exit_without_execution(self):
        rows = [
            self._row(0, BaselineDecision.LONG),
            self._row(1, BaselineDecision.LONG, price=101.0),
            self._row(2, BaselineDecision.SHORT, price=102.0),
            self._row(3, BaselineDecision.SHORT, price=101.0),
            self._row(4, BaselineDecision.NO_TRADE, RiskDecision.VETO, price=100.0),
        ]

        result = PaperValidation().run(rows)

        self.assertEqual(result.events, 5)
        self.assertEqual(result.entries, 2)
        self.assertEqual(result.exits, 2)
        self.assertEqual(result.holds, 1)
        self.assertEqual(result.no_trade, 0)
        self.assertEqual(result.vetoed, 0)
        self.assertEqual(result.final_state, PaperState.FLAT)

    def test_veto_closes_existing_position(self):
        rows = [
            self._row(0, BaselineDecision.LONG),
            self._row(1, BaselineDecision.LONG, price=101.0),
            self._row(2, BaselineDecision.LONG, RiskDecision.VETO, price=102.0),
        ]

        result = PaperValidation().run(rows)

        self.assertEqual(result.entries, 1)
        self.assertEqual(result.exits, 1)
        self.assertEqual(result.holds, 1)
        self.assertEqual(result.final_state, PaperState.FLAT)

    def test_flat_no_trade_does_not_create_position(self):
        rows = [
            self._row(0, BaselineDecision.NO_TRADE, RiskDecision.VETO),
            self._row(1, BaselineDecision.NO_TRADE, RiskDecision.VETO, price=101.0),
        ]

        result = PaperValidation().run(rows)

        self.assertEqual(result.events, 2)
        self.assertEqual(result.entries, 0)
        self.assertEqual(result.exits, 0)
        self.assertEqual(result.no_trade, 2)
        self.assertEqual(result.final_state, PaperState.FLAT)


if __name__ == "__main__":
    unittest.main()
