"""Tests for frozen fold-by-fold OOS cost/slippage measurement."""

import unittest
from datetime import datetime, timedelta, timezone

from core.backtest.costs import CostScenario
from core.backtest.engine import BacktestResult, BacktestSample
from core.backtest.oos_cost_matrix import evaluate_oos_cost_matrix
from core.backtest.oos_protocol import REAL_BTC_USDT_OOS_V1
from core.backtest.walk_forward import WalkForwardFold, WalkForwardResult
from core.risk.boundary import RiskDecision
from core.strategy.baseline import BaselineDecision


def make_fold(index: int) -> WalkForwardFold:
    base = datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(days=index)
    sample = BacktestSample(
        base, BaselineDecision.LONG, RiskDecision.ALLOW_SIGNAL, 100.0, 101.0
    )
    result = BacktestResult(
        samples=1, evaluated=1, vetoed=0, no_trade=0,
        wins=1, losses=0, total_return=0.01, win_rate=1.0,
    )
    return WalkForwardFold(
        index=index,
        train_start=base - timedelta(minutes=2),
        train_end=base - timedelta(minutes=1),
        test_start=base,
        test_end=base,
        train_observations=800,
        test_observations=400,
        result=result,
        test_samples=(sample,),
    )


class OOSCostMatrixTests(unittest.TestCase):
    def test_requires_frozen_fold_count(self):
        result = WalkForwardResult(
            folds=tuple(make_fold(i) for i in range(7)),
            samples=7, evaluated=7, vetoed=0, no_trade=0,
            wins=7, losses=0, total_return=0.07, win_rate=1.0,
        )
        with self.assertRaisesRegex(ValueError, "requires 8 folds"):
            evaluate_oos_cost_matrix(
                result, REAL_BTC_USDT_OOS_V1, (CostScenario(0.0, 0.0),)
            )

    def test_measures_every_fold_and_aggregates_each_scenario(self):
        result = WalkForwardResult(
            folds=tuple(make_fold(i) for i in range(8)),
            samples=8, evaluated=8, vetoed=0, no_trade=0,
            wins=8, losses=0, total_return=0.08, win_rate=1.0,
        )
        scenarios = (CostScenario(0.0, 0.0), CostScenario(5.0, 2.0))
        matrix = evaluate_oos_cost_matrix(result, REAL_BTC_USDT_OOS_V1, scenarios)

        self.assertEqual(matrix.protocol_id, REAL_BTC_USDT_OOS_V1.protocol_id)
        self.assertEqual(matrix.fold_count, 8)
        self.assertEqual(len(matrix.measurements), 16)
        self.assertEqual(len(matrix.aggregate), 2)
        self.assertAlmostEqual(matrix.aggregate[0].total_net_return, 0.08)
        self.assertAlmostEqual(matrix.aggregate[1].total_net_return, 0.0688)
        self.assertEqual(matrix.aggregate[1].evaluated, 8)


if __name__ == "__main__":
    unittest.main()
