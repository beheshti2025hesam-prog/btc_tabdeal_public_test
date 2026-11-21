"""Tests for configurable cost/slippage scenario measurement."""

import unittest
from datetime import datetime, timezone

from core.backtest.costs import CostScenario, evaluate_samples
from core.backtest.engine import BacktestSample
from core.risk.boundary import RiskDecision
from core.strategy.baseline import BaselineDecision


class CostScenarioTests(unittest.TestCase):
    def test_matrix_changes_net_return_only_by_explicit_cost_assumption(self):
        ts = datetime(2026, 9, 25, tzinfo=timezone.utc)
        sample = BacktestSample(
            ts, BaselineDecision.LONG, RiskDecision.ALLOW_SIGNAL, 100.0, 101.0
        )
        scenarios = (
            CostScenario(0.0, 0.0),
            CostScenario(5.0, 2.0),
            CostScenario(10.0, 5.0),
        )
        results = evaluate_samples((sample,), scenarios)
        self.assertEqual([r[2] for r in results], [1, 1, 1])
        self.assertAlmostEqual(results[0][1], 0.01)
        self.assertAlmostEqual(results[1][1], 0.0086)
        self.assertAlmostEqual(results[2][1], 0.007)
    
    def test_veto_and_no_trade_do_not_enter_matrix(self):
        ts = datetime(2026, 9, 25, tzinfo=timezone.utc)
        samples = (
            BacktestSample(ts, BaselineDecision.NO_TRADE, RiskDecision.ALLOW_SIGNAL, 100, 101),
            BacktestSample(ts, BaselineDecision.LONG, RiskDecision.VETO, 100, 101),
        )
        results = evaluate_samples(samples, (CostScenario(5, 2),))
        self.assertEqual(results[0][2:], (0, 0, 0))


if __name__ == "__main__":
    unittest.main()
