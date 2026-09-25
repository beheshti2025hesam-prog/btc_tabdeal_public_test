"""Tests for strict chronological OOS / walk-forward validation."""
import unittest
from datetime import datetime, timedelta, timezone

from core.backtest.engine import BacktestSample
from core.backtest.validation import HistoricalObservation
from core.backtest.walk_forward import WalkForwardValidation
from core.risk.boundary import RiskDecision
from core.strategy.baseline import BaselineDecision


class WalkForwardValidationTests(unittest.TestCase):
    def observations(self, count=12):
        rows = []
        base = datetime(2026, 9, 25, tzinfo=timezone.utc)
        for i in range(count):
            ts = base + timedelta(minutes=i)
            rows.append(
                HistoricalObservation(
                    ts,
                    BacktestSample(
                        ts,
                        BaselineDecision.LONG,
                        RiskDecision.ALLOW_SIGNAL,
                        100.0,
                        101.0,
                    ),
                )
            )
        return rows

    def test_creates_non_overlapping_chronological_oos_folds(self):
        result = WalkForwardValidation(
            train_size=4,
            test_size=2,
            step_size=2,
        ).run(self.observations())

        self.assertEqual(len(result.folds), 4)
        self.assertEqual(result.samples, 8)
        self.assertEqual(result.evaluated, 8)
        self.assertEqual(result.wins, 8)

        for fold in result.folds:
            self.assertLess(fold.train_end, fold.test_start)
            self.assertEqual(fold.train_observations, 4)
            self.assertEqual(fold.test_observations, 2)

    def test_embargo_separates_train_and_test(self):
        result = WalkForwardValidation(
            train_size=3,
            test_size=2,
            step_size=2,
            embargo_size=1,
        ).run(self.observations(8))

        first = result.folds[0]
        self.assertEqual(first.train_end + timedelta(minutes=2), first.test_start)

    def test_rejects_insufficient_history(self):
        with self.assertRaises(ValueError):
            WalkForwardValidation(train_size=5, test_size=2).run(self.observations(6))

    def test_rejects_overlapping_oos_configuration(self):
        with self.assertRaises(ValueError):
            WalkForwardValidation(train_size=4, test_size=3, step_size=2)

    def test_rejects_invalid_configuration(self):
        with self.assertRaises(ValueError):
            WalkForwardValidation(train_size=0, test_size=2)
        with self.assertRaises(ValueError):
            WalkForwardValidation(train_size=2, test_size=0)
        with self.assertRaises(ValueError):
            WalkForwardValidation(train_size=2, test_size=2, embargo_size=-1)


if __name__ == "__main__":
    unittest.main()
