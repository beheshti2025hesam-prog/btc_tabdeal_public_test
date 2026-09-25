"""Tests for execution-free paper performance measurement."""
import unittest
from datetime import datetime, timezone

from core.backtest.engine import BacktestSample
from core.backtest.validation import HistoricalObservation
from core.paper.performance import PaperPerformance
from core.paper.session import PaperState
from core.risk.boundary import RiskDecision
from core.strategy.baseline import BaselineDecision


class PaperPerformanceTests(unittest.TestCase):
    def row(self, minute, decision, price, risk=RiskDecision.ALLOW_SIGNAL):
        ts = datetime(2026, 9, 25, 0, minute, tzinfo=timezone.utc)
        return HistoricalObservation(ts, BacktestSample(ts, decision, risk, price, price))

    def test_measures_completed_virtual_trade_without_capital_or_leverage(self):
        rows = [
            self.row(0, BaselineDecision.LONG, 100.0),
            self.row(1, BaselineDecision.LONG, 102.0),
            self.row(2, BaselineDecision.NO_TRADE, 105.0, RiskDecision.VETO),
            self.row(3, BaselineDecision.SHORT, 105.0),
            self.row(4, BaselineDecision.SHORT, 103.0),
            self.row(5, BaselineDecision.NO_TRADE, 100.0, RiskDecision.VETO),
        ]

        result = PaperPerformance().run(rows)

        self.assertEqual(result.completed_trades, 2)
        self.assertEqual(result.wins, 2)
        self.assertEqual(result.losses, 0)
        self.assertEqual(result.flat_trades, 0)
        self.assertEqual(result.win_rate, 1.0)
        self.assertAlmostEqual(result.total_return, 0.06904761904761905, places=6)
        self.assertEqual(result.max_drawdown, 0.0)
        self.assertEqual(result.open_state, PaperState.FLAT)

    def test_open_position_is_reported_not_realized(self):
        rows = [self.row(0, BaselineDecision.LONG, 100.0), self.row(1, BaselineDecision.LONG, 110.0)]
        result = PaperPerformance().run(rows)
        self.assertEqual(result.completed_trades, 0)
        self.assertEqual(result.open_state, PaperState.LONG)


if __name__ == "__main__":
    unittest.main()
