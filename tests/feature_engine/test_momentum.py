"""Deterministic momentum contract tests for HES Trade Agent."""
import unittest
from datetime import datetime, timedelta, timezone

from core.data_engine.candles import Candle
from core.feature_engine.momentum import MomentumCalculator


class MomentumCalculatorTests(unittest.TestCase):
    def _candles(self, closes):
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        return [
            Candle(
                symbol="BTC_USDT", timeframe_seconds=60,
                start=start + timedelta(minutes=i),
                end=start + timedelta(minutes=i + 1),
                open=value, high=value, low=value, close=value,
                volume=1.0, trade_count=1,
            )
            for i, value in enumerate(closes)
        ]

    def test_momentum_is_deterministic(self):
        snapshots = MomentumCalculator(period=2).calculate(
            self._candles([100.0, 102.0, 105.0, 101.0])
        )
        self.assertEqual(len(snapshots), 2)
        self.assertAlmostEqual(snapshots[0].value, 5.0)
        self.assertAlmostEqual(snapshots[0].value_pct, 5.0)
        self.assertAlmostEqual(snapshots[1].value, -1.0)
        self.assertAlmostEqual(snapshots[1].value_pct, -0.9803921569)

    def test_insufficient_history_returns_no_snapshot(self):
        self.assertEqual(
            MomentumCalculator(period=3).calculate(self._candles([1.0, 2.0, 3.0])),
            [],
        )

    def test_invalid_period_is_rejected(self):
        with self.assertRaises(ValueError):
            MomentumCalculator(period=0)

    def test_naive_timestamp_is_rejected(self):
        candles = self._candles([1.0, 2.0, 3.0])
        c = candles[0]
        candles[0] = Candle(
            c.symbol, c.timeframe_seconds, c.start.replace(tzinfo=None), c.end,
            c.open, c.high, c.low, c.close, c.volume, c.trade_count,
        )
        with self.assertRaises(ValueError):
            MomentumCalculator(period=1).calculate(candles)

    def test_zero_reference_close_is_rejected(self):
        candles = self._candles([0.0, 1.0])
        with self.assertRaises(ValueError):
            MomentumCalculator(period=1).calculate(candles)

    def test_non_finite_close_is_rejected(self):
        candles = self._candles([1.0, 2.0])
        c = candles[1]
        candles[1] = Candle(
            c.symbol, c.timeframe_seconds, c.start, c.end,
            c.open, c.high, c.low, float("inf"), c.volume, c.trade_count,
        )
        with self.assertRaises(ValueError):
            MomentumCalculator(period=1).calculate(candles)


if __name__ == "__main__":
    unittest.main()
