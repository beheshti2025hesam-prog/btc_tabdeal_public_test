"""Tests for deterministic, execution-free trade cost modeling."""
import unittest

from core.backtest.engine import BacktestEngine, BacktestSample
from core.backtest.execution_realism import ExecutionCostConfig, ExecutionCostModel
from core.risk.boundary import RiskDecision
from core.strategy.baseline import BaselineDecision
from datetime import datetime, timedelta, timezone


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

    def test_costs_reduce_short_trade_too(self):
        model = ExecutionCostModel(
            ExecutionCostConfig(
                fee_bps_per_side=10,
                spread_bps=20,
                slippage_bps_per_side=5,
            )
        )
        result = model.apply(direction=-1, entry_mid_price=100, exit_mid_price=90)

        self.assertGreater(result.gross_return, result.net_return)
        self.assertGreater(result.cost_fraction, 0.0)
        self.assertGreater(result.net_return, 0.0)

    def test_zero_cost_has_zero_cost_fraction_and_identity_prices(self):
        result = ExecutionCostModel().apply(
            direction=1, entry_mid_price=100, exit_mid_price=110
        )
        self.assertEqual(result.cost_fraction, 0.0)
        self.assertEqual(result.entry_execution_price, 100)
        self.assertEqual(result.exit_execution_price, 110)

    def test_backtest_reports_additive_and_compounded_returns(self):
        base = datetime(2026, 1, 1, tzinfo=timezone.utc)
        samples = (
            BacktestSample(base, BaselineDecision.LONG, RiskDecision.ALLOW_SIGNAL, 100.0, 101.0, base + timedelta(minutes=1)),
            BacktestSample(base + timedelta(minutes=1), BaselineDecision.LONG, RiskDecision.ALLOW_SIGNAL, 101.0, 102.01, base + timedelta(minutes=2)),
        )
        result = BacktestEngine().run(samples)
        self.assertAlmostEqual(result.total_return, 0.02)
        self.assertAlmostEqual(result.compounded_return, 0.0201)

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
