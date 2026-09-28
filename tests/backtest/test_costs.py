"""Tests for the explicit backtest execution-cost boundary."""
import unittest
from datetime import datetime, timezone

from core.backtest.costs import BacktestCostModel, CostScenario, evaluate_samples
from core.backtest.engine import BacktestSample
from core.risk.boundary import RiskDecision
from core.strategy.baseline import BaselineDecision


class BacktestCostModelTests(unittest.TestCase):
    def setUp(self):
        self.ts = datetime(2026, 9, 25, tzinfo=timezone.utc)

    def sample(self, decision, entry=100.0, exit=101.0):
        return BacktestSample(
            self.ts, decision, RiskDecision.ALLOW_SIGNAL, entry, exit
        )

    def test_zero_cost_matches_gross_return(self):
        model = BacktestCostModel()
        sample = self.sample(BaselineDecision.LONG)
        self.assertAlmostEqual(model.gross_return(sample), 0.01)
        self.assertAlmostEqual(model.net_return(sample), 0.01)

    def test_transaction_cost_and_slippage_apply_on_both_sides(self):
        model = BacktestCostModel(
            transaction_cost_bps_per_side=5.0,
            slippage_bps_per_side=2.0,
        )
        sample = self.sample(BaselineDecision.LONG)
        self.assertAlmostEqual(model.net_return(sample), 0.0086)

    def test_short_is_directional_but_cost_is_always_adverse(self):
        model = BacktestCostModel(transaction_cost_bps_per_side=5.0)
        sample = self.sample(BaselineDecision.SHORT, entry=100.0, exit=99.0)
        self.assertAlmostEqual(model.net_return(sample), 0.009)

    def test_invalid_assumptions_fail_closed(self):
        with self.assertRaises(ValueError):
            BacktestCostModel(transaction_cost_bps_per_side=-1)
        with self.assertRaises(ValueError):
            BacktestCostModel(slippage_bps_per_side=float("nan"))

    def test_cost_scenario_also_rejects_invalid_assumptions(self):
        with self.assertRaises(ValueError):
            CostScenario(transaction_cost_bps_per_side=-1, slippage_bps_per_side=0)
        with self.assertRaises(ValueError):
            CostScenario(transaction_cost_bps_per_side=0, slippage_bps_per_side=float("inf"))

    def test_non_finite_prices_fail_closed(self):
        model = BacktestCostModel()
        with self.assertRaises(ValueError):
            model.net_return(self.sample(BaselineDecision.LONG, entry=float("nan")))
        with self.assertRaises(ValueError):
            model.gross_return(self.sample(BaselineDecision.SHORT, exit=float("inf")))

    def test_non_trade_cannot_be_costed(self):
        model = BacktestCostModel()
        with self.assertRaises(ValueError):
            model.net_return(self.sample(BaselineDecision.NO_TRADE))

    def test_generator_is_evaluated_for_every_scenario(self):
        samples = (sample for sample in (self.sample(BaselineDecision.LONG),))
        results = evaluate_samples(
            samples,
            (CostScenario(0.0, 0.0), CostScenario(5.0, 2.0)),
        )
        self.assertEqual([row[2] for row in results], [1, 1])
        self.assertAlmostEqual(results[0][1], 0.01)
        self.assertAlmostEqual(results[1][1], 0.0086)

    def test_empty_scenarios_fail_closed(self):
        with self.assertRaises(ValueError):
            evaluate_samples((self.sample(BaselineDecision.LONG),), ())


if __name__ == "__main__":
    unittest.main()
