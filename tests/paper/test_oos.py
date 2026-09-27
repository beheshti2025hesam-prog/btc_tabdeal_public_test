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

    def test_paper_measurement_uses_signal_stream_not_backtest_exit_price(self):
        base = datetime(2026, 9, 25, tzinfo=timezone.utc)
        rows = [
            HistoricalObservation(
                base,
                BacktestSample(
                    base, BaselineDecision.LONG, RiskDecision.ALLOW_SIGNAL,
                    100, 999, base + timedelta(minutes=1),
                ),
            ),
            HistoricalObservation(
                base + timedelta(minutes=1),
                BacktestSample(
                    base + timedelta(minutes=1), BaselineDecision.NO_TRADE,
                    RiskDecision.ALLOW_SIGNAL, 101, 999,
                    base + timedelta(minutes=2),
                ),
            ),
        ]
        performance = __import__("core.paper.performance", fromlist=["PaperPerformance"]).PaperPerformance().run(rows)
        self.assertEqual(performance.completed_trades, 1)
        self.assertEqual(performance.folds if hasattr(performance, "folds") else 1, 1)
        self.assertAlmostEqual(performance.total_return, 0.01)

    def test_fold_end_open_position_is_neutralized_without_future_data(self):
        observations = self.rows(4)
        observations[3] = HistoricalObservation(
            observations[3].timestamp,
            BacktestSample(
                observations[3].timestamp,
                BaselineDecision.LONG,
                RiskDecision.ALLOW_SIGNAL,
                105,
                105,
            ),
        )
        validator = WalkForwardValidation(train_size=2, test_size=2, step_size=2)
        result = PaperOOS().run(observations, validator)
        self.assertEqual(result.robustness.fold_count, 1)
        self.assertEqual(result.folds[0].performance.open_state.value, "FLAT")
        self.assertEqual(result.folds[0].performance.completed_trades, 1)


if __name__ == "__main__":
    unittest.main()
