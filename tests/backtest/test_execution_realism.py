"""Tests for deterministic, execution-free trade cost modeling."""
import unittest

from core.backtest.execution_realism import ExecutionCostConfig, ExecutionCostModel


class ExecutionCostModelTests(unittest.TestCase):
    def test_zero_cost_preserves_directional_result(self):
        model = ExecutionCostModel()
        long_trade = model.apply(direction=1, entry_mid_price=100, exit_mid_price=110)
        short_trade = model.apply(direction=-1, entry_mid_price=100, exit_mid_price=90)

        self.assertAlmostEqual(long_trade.net_return, 0.10)
        self.assertAlmostEqual(short_trade.net_return, 0.10)

    def test_costs_reduce_a_winning_trade(self):
        model = ExecutionCostModel(
            ExecutionCostConfig(
                fee_bps_per_side=10,
                spread_bps=20,
                slippage_bps_per_side=5,
            )
        )
        result = model.apply(direction=1, entry_mid_price=100, exit_mid_price=110)

        self.assertGreater(result.gross_return, result.net_return)
        self.assertGreater(result.cost_fraction, 0.0)
        self.assertGreater(result.net_return, 0.0)

    def test_costs_can_turn_a_marginal_trade_into_a_loss(self):
        model = ExecutionCostModel(
            ExecutionCostConfig(
                fee_bps_per_side=20,
                spread_bps=40,
                slippage_bps_per_side=20,
            )
        )
        result = model.apply(direction=1, entry_mid_price=100, exit_mid_price=100.02)

        self.assertLessEqual(result.net_return, 0.0)

    def test_invalid_parameters_are_rejected(self):
        with self.assertRaises(ValueError):
            ExecutionCostConfig(fee_bps_per_side=-1)
        with self.assertRaises(ValueError):
            ExecutionCostConfig(spread_bps=20000)

    def test_latency_and_funding_are_not_silently_assumed(self):
        config = ExecutionCostConfig()
        self.assertEqual(config.fee_bps_per_side, 0.0)
        self.assertEqual(config.spread_bps, 0.0)
        self.assertEqual(config.slippage_bps_per_side, 0.0)


if __name__ == "__main__":
    unittest.main()
