"""Tests for execution-free OOS fold stability measurement."""
import unittest
from datetime import datetime, timedelta, timezone

from core.backtest.engine import BacktestResult
from core.backtest.robustness import OOSStabilityMeasurement
from core.backtest.walk_forward import WalkForwardFold, WalkForwardResult


class OOSStabilityMeasurementTests(unittest.TestCase):
    def make_result(self):
        base = datetime(2026, 9, 25, tzinfo=timezone.utc)
        fold_results = (
            BacktestResult(2, 2, 0, 0, 2, 0, 0.10, 1.0),
            BacktestResult(2, 2, 0, 0, 1, 1, 0.00, 0.5),
            BacktestResult(2, 2, 0, 0, 0, 2, -0.20, 0.0),
        )
        folds = []
        for index, result in enumerate(fold_results):
            train_start = base + timedelta(minutes=index * 4)
            train_end = train_start + timedelta(minutes=1)
            test_start = train_start + timedelta(minutes=2)
            test_end = test_start + timedelta(minutes=1)
            folds.append(
                WalkForwardFold(
                    index=index,
                    train_start=train_start,
                    train_end=train_end,
                    test_start=test_start,
                    test_end=test_end,
                    train_observations=2,
                    test_observations=2,
                    result=result,
                )
            )
        return WalkForwardResult(
            folds=tuple(folds),
            samples=6,
            evaluated=6,
            vetoed=0,
            no_trade=0,
            wins=3,
            losses=3,
            total_return=-0.10,
            win_rate=0.5,
        )

    def test_measures_fold_dispersion_without_replaying_data(self):
        result = OOSStabilityMeasurement().run(self.make_result())

        self.assertEqual(result.fold_count, 3)
        self.assertAlmostEqual(result.mean_win_rate, 0.5)
        self.assertAlmostEqual(result.min_win_rate, 0.0)
        self.assertAlmostEqual(result.max_win_rate, 1.0)
        self.assertAlmostEqual(result.win_rate_range, 1.0)
        self.assertAlmostEqual(result.mean_return, -0.10 / 3)
        self.assertAlmostEqual(result.min_return, -0.20)
        self.assertAlmostEqual(result.max_return, 0.10)
        self.assertAlmostEqual(result.return_range, 0.30)
        self.assertEqual(result.positive_return_folds, 1)
        self.assertEqual(result.negative_return_folds, 1)
        self.assertEqual(result.flat_return_folds, 1)

    def test_rejects_empty_fold_result(self):
        empty = WalkForwardResult((), 0, 0, 0, 0, 0, 0, 0.0, 0.0)
        with self.assertRaises(ValueError):
            OOSStabilityMeasurement().run(empty)


if __name__ == "__main__":
    unittest.main()
