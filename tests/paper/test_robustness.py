"""Tests for execution-free paper robustness measurement."""
import unittest
from datetime import datetime, timezone

from core.backtest.engine import BacktestSample
from core.backtest.validation import HistoricalObservation
from core.paper.robustness import PaperRobustness
from core.risk.boundary import RiskDecision
from core.strategy.baseline import BaselineDecision


class PaperRobustnessTests(unittest.TestCase):
    def row(self, minute, decision, price, risk=RiskDecision.ALLOW_SIGNAL):
        ts = datetime(2026, 9, 25, 0, minute, tzinfo=timezone.utc)
        return HistoricalObservation(ts, BacktestSample(ts, decision, risk, price, price))

    def test_measures_closed_folds(self):
        folds = [
            [
                self.row(0, BaselineDecision.LONG, 100),
                self.row(1, BaselineDecision.NO_TRADE, 105, RiskDecision.VETO),
            ],
            [
                self.row(2, BaselineDecision.SHORT, 100),
                self.row(3, BaselineDecision.NO_TRADE, 95, RiskDecision.VETO),
            ],
        ]

        result = PaperRobustness().run(folds)

        self.assertEqual(result.fold_count, 2)
        self.assertEqual(result.positive_folds, 2)
        self.assertEqual(result.negative_folds, 0)
        self.assertAlmostEqual(result.mean_win_rate, 1.0)
        self.assertAlmostEqual(result.mean_return, 0.05)
        self.assertAlmostEqual(result.win_rate_range, 0.0)

    def test_rejects_open_fold(self):
        folds = [[self.row(0, BaselineDecision.LONG, 100)]]
        with self.assertRaises(ValueError):
            PaperRobustness().run(folds)


if __name__ == "__main__":
    unittest.main()
