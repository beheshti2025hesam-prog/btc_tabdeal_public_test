"""Backtest engine safety and determinism tests."""
import unittest
from datetime import datetime, timezone

from core.backtest.engine import BacktestEngine, BacktestSample
from core.risk.boundary import RiskDecision
from core.strategy.baseline import BaselineDecision


class BacktestEngineTests(unittest.TestCase):
    def setUp(self):
        self.engine = BacktestEngine()
        self.ts = datetime(2026, 9, 25, tzinfo=timezone.utc)

    def test_long_and_short_returns_are_directional(self):
        result = self.engine.run([
            BacktestSample(self.ts, BaselineDecision.LONG, RiskDecision.ALLOW_SIGNAL, 100, 110),
            BacktestSample(self.ts, BaselineDecision.SHORT, RiskDecision.ALLOW_SIGNAL, 100, 90),
        ])
        self.assertEqual(result.evaluated, 2)
        self.assertEqual(result.wins, 2)
        self.assertEqual(result.losses, 0)
        self.assertAlmostEqual(result.total_return, 0.20)
        self.assertEqual(result.win_rate, 1.0)

    def test_veto_and_no_trade_do_not_count_as_evaluated(self):
        result = self.engine.run([
            BacktestSample(self.ts, BaselineDecision.LONG, RiskDecision.VETO, 100, 50),
            BacktestSample(self.ts, BaselineDecision.NO_TRADE, RiskDecision.VETO, 100, 50),
        ])
        self.assertEqual(result.evaluated, 0)
        self.assertEqual(result.vetoed, 1)
        self.assertEqual(result.no_trade, 1)
        self.assertEqual(result.total_return, 0.0)

    def test_naive_timestamp_is_rejected(self):
        with self.assertRaises(ValueError):
            self.engine.run([
                BacktestSample(
                    datetime(2026, 9, 25),
                    BaselineDecision.LONG,
                    RiskDecision.ALLOW_SIGNAL,
                    100,
                    101,
                )
            ])


if __name__ == "__main__":
    unittest.main()
