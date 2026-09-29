"""Tests for the frozen OOS execution-cost matrix."""
import unittest
from datetime import datetime, timezone

from core.backtest.engine import BacktestResult, BacktestSample
from core.backtest.execution_realism import ExecutionCostConfig
from core.backtest.oos_cost_matrix import OOSCostScenario, evaluate_oos_cost_matrix
from core.backtest.oos_protocol import REAL_BTC_USDT_OOS_V1
from core.backtest.validation import HistoricalObservation
from core.backtest.walk_forward import WalkForwardFold, WalkForwardResult
from core.risk.boundary import RiskDecision
from core.strategy.baseline import BaselineDecision


def make_fold(index: int) -> WalkForwardFold:
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    sample = BacktestSample(
        base, BaselineDecision.LONG, RiskDecision.ALLOW_SIGNAL, 100.0, 101.0,
        base.replace(second=30),
    )
    result = BacktestResult(1, 1, 0, 0, 1, 0, 0.01, 1.0)
    return WalkForwardFold(
        index=index,
        train_start=base,
        train_end=base,
        test_start=base,
        test_end=base,
        train_observations=800,
        test_observations=400,
        train=( ),
        test=(HistoricalObservation(base, sample),),
        result=result,
    )


class OOSCostMatrixTests(unittest.TestCase):
    def scenarios(self):
        return (
            OOSCostScenario("zero", ExecutionCostConfig()),
            OOSCostScenario(
                "costed",
                ExecutionCostConfig(fee_bps_per_side=5.0, slippage_bps_per_side=2.0),
            ),
        )

    def test_requires_frozen_fold_count(self):
        result = WalkForwardResult(
            folds=tuple(make_fold(i) for i in range(7)),
            samples=7, evaluated=7, vetoed=0, no_trade=0,
            wins=7, losses=0, total_return=0.07, win_rate=1.0,
        )
        with self.assertRaisesRegex(ValueError, "requires 8 folds"):
            evaluate_oos_cost_matrix(result, REAL_BTC_USDT_OOS_V1, self.scenarios())

    def test_measures_every_fold_and_aggregates(self):
        result = WalkForwardResult(
            folds=tuple(make_fold(i) for i in range(8)),
            samples=8, evaluated=8, vetoed=0, no_trade=0,
            wins=8, losses=0, total_return=0.08, win_rate=1.0,
        )
        matrix = evaluate_oos_cost_matrix(result, REAL_BTC_USDT_OOS_V1, self.scenarios())
        self.assertEqual(matrix.fold_count, 8)
        self.assertEqual(len(matrix.measurements), 16)
        self.assertEqual(len(matrix.aggregate), 2)
        self.assertAlmostEqual(matrix.aggregate[0].total_net_return, 0.08)
        self.assertLess(matrix.aggregate[1].total_net_return, matrix.aggregate[0].total_net_return)


if __name__ == "__main__":
    unittest.main()
