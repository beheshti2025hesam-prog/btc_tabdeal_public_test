"""Deterministic EMA contract tests for HES Trade Agent."""
import unittest
from datetime import datetime, timedelta, timezone

from core.data_engine.candles import Candle
from core.feature_engine.ema import EMACalculator


class EMACalculatorTests(unittest.TestCase):
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

    def test_seed_and_recursive_ema_are_deterministic(self):
        snapshots = EMACalculator(period=3).calculate(self._candles([1.0, 2.0, 3.0, 6.0]))
        self.assertEqual(len(snapshots), 2)
        self.assertAlmostEqual(snapshots[0].value, 2.0)
        self.assertAlmostEqual(snapshots[1].value, 4.0)
        self.assertEqual(snapshots[0].timestamp.tzinfo, timezone.utc)

    def test_insufficient_history_returns_no_snapshot(self):
        self.assertEqual(EMACalculator(period=4).calculate(self._candles([1.0, 2.0, 3.0])), [])

    def test_invalid_period_is_rejected(self):
        with self.assertRaises(ValueError):
            EMACalculator(period=0)

    def test_naive_timestamp_is_rejected(self):
        candles = self._candles([1.0, 2.0, 3.0])
        candles[0] = Candle(
            symbol=candles[0].symbol, timeframe_seconds=60,
            start=candles[0].start.replace(tzinfo=None), end=candles[0].end,
            open=1.0, high=1.0, low=1.0, close=1.0, volume=1.0, trade_count=1,
        )
        with self.assertRaises(ValueError):
            EMACalculator(period=3).calculate(candles)

    def test_non_finite_close_is_rejected(self):
        candles = self._candles([1.0, 2.0, 3.0])
        candles[1] = Candle(
            symbol="BTC_USDT", timeframe_seconds=60,
            start=candles[1].start, end=candles[1].end,
            open=2.0, high=2.0, low=2.0, close=float("nan"),
            volume=1.0, trade_count=1,
        )
        with self.assertRaises(ValueError):
            EMACalculator(period=3).calculate(candles)


if __name__ == "__main__":
    unittest.main()
