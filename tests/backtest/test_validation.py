"""Historical validation anti-leakage boundary tests."""
import unittest
from datetime import datetime, timezone

from core.backtest.engine import BacktestSample
from core.backtest.validation import HistoricalObservation, HistoricalValidation
from core.risk.boundary import RiskDecision
from core.strategy.baseline import BaselineDecision


class HistoricalValidationTests(unittest.TestCase):
    def setUp(self):
        self.validation = HistoricalValidation()
        self.t1 = datetime(2026, 9, 25, 10, tzinfo=timezone.utc)
        self.t2 = datetime(2026, 9, 25, 11, tzinfo=timezone.utc)

    def sample(self, ts, entry, exit):
        return BacktestSample(ts, BaselineDecision.LONG, RiskDecision.ALLOW_SIGNAL, entry, exit)

    def test_accepts_chronological_history(self):
        result = self.validation.run([
            HistoricalObservation(self.t1, self.sample(self.t1, 100, 101)),
            HistoricalObservation(self.t2, self.sample(self.t2, 101, 102)),
        ])
        self.assertEqual(result.samples, 2)
        self.assertEqual(result.wins, 2)

    def test_rejects_backward_history(self):
        with self.assertRaises(ValueError):
            self.validation.run([
                HistoricalObservation(self.t2, self.sample(self.t2, 100, 101)),
                HistoricalObservation(self.t1, self.sample(self.t1, 101, 102)),
            ])

    def test_rejects_timestamp_mismatch(self):
        with self.assertRaises(ValueError):
            self.validation.run([
                HistoricalObservation(self.t1, self.sample(self.t2, 100, 101)),
            ])


if __name__ == "__main__":
    unittest.main()
