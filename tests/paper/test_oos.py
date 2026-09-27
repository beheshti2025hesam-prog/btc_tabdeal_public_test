"""Tests for execution-free chronological paper OOS integration."""
import unittest
from datetime import datetime, timedelta, timezone

from core.backtest.engine import BacktestSample
from core.backtest.validation import HistoricalObservation
from core.backtest.walk_forward import WalkForwardValidation
from core.paper.oos import PaperOOS
from core.risk.boundary import RiskDecision
from core.strategy.baseline import BaselineDecision


class PaperOOSTests(unittest.TestCase):
    def rows(self, count=8):
        base = datetime(2026, 9, 25, tzinfo=timezone.utc)
        rows = []
        for i in range(count):
            ts = base + timedelta(minutes=i)
            decision = BaselineDecision.LONG if i % 2 == 0 else BaselineDecision.NO_TRADE
            price = 100 + (5 if i % 2 else 0)
            rows.append(
                HistoricalObservation(
                    ts,
                    BacktestSample(
                        ts, decision, RiskDecision.ALLOW_SIGNAL, price, price
                    ),
                )
            )
        return rows

    def test_uses_only_oos_test_for_paper_measurement(self):
        observations = self.rows()
        validator = WalkForwardValidation(train_size=4, test_size=2, step_size=2)
        result = PaperOOS().run(observations, validator)

        self.assertEqual(len(result.folds), 2)
        self.assertEqual(len(result.folds[0].train), 4)
        self.assertEqual(len(result.folds[0].test), 2)
        self.assertEqual(result.robustness.fold_count, 2)
        self.assertEqual(result.folds[0].test[0].timestamp, observations[4].timestamp)
        self.assertEqual(result.folds[1].test[0].timestamp, observations[6].timestamp)

    def test_rejects_empty_input(self):
        validator = WalkForwardValidation(train_size=2, test_size=1, step_size=1)
        with self.assertRaises(ValueError):
            PaperOOS().run([], validator)


    def test_future_extension_does_not_change_existing_fold_measurement(self):
        observations = self.rows(8)
        extended = self.rows(12)
        validator = WalkForwardValidation(train_size=4, test_size=2, step_size=2)

        base = PaperOOS().run(observations, validator)
        future = PaperOOS().run(extended, validator)

        self.assertEqual(len(base.folds), 2)
        self.assertGreaterEqual(len(future.folds), 2)

        for before, after in zip(base.folds, future.folds):
            self.assertEqual(before.test, after.test)
            self.assertEqual(before.performance, after.performance)

    def test_fold_with_unclosed_position_is_rejected_by_robustness(self):
        observations = self.rows(5)
        validator = WalkForwardValidation(train_size=2, test_size=2, step_size=2)
        with self.assertRaises(ValueError):
            PaperOOS().run(observations, validator)


if __name__ == "__main__":
    unittest.main()
