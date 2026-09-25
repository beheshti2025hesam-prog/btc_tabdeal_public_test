"""Deterministic swing structure contract tests for HES Trade Agent."""
import unittest
from datetime import datetime, timedelta, timezone
from core.data_engine.candles import Candle
from core.feature_engine.structure import StructureCalculator


class StructureCalculatorTests(unittest.TestCase):
    def _candles(self, highs, lows):
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        return [Candle("BTC_USDT", 60, start + timedelta(minutes=i), start + timedelta(minutes=i+1),
                       low, high, low, high, 1.0, 1)
                for i, (high, low) in enumerate(zip(highs, lows))]

    def test_confirmed_swings_are_deterministic(self):
        result = StructureCalculator(1, 1).calculate(
            self._candles([10, 12, 15, 13, 11], [8, 9, 10, 7, 9]))
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0].swing_high, 15)
        self.assertIsNone(result[0].swing_low)
        self.assertEqual(result[1].swing_low, 7)
        self.assertEqual(result[1].swing_high, 15)

    def test_insufficient_history_returns_no_snapshot(self):
        self.assertEqual(StructureCalculator(2, 2).calculate(self._candles([10, 11], [8, 9])), [])

    def test_invalid_window_is_rejected(self):
        with self.assertRaises(ValueError):
            StructureCalculator(0, 2)
        with self.assertRaises(ValueError):
            StructureCalculator(2, 0)

    def test_naive_timestamp_is_rejected(self):
        candles = self._candles([10, 11, 12], [8, 9, 10])
        c = candles[0]
        candles[0] = Candle(c.symbol, c.timeframe_seconds, c.start.replace(tzinfo=None), c.end,
                             c.open, c.high, c.low, c.close, c.volume, c.trade_count)
        with self.assertRaises(ValueError):
            StructureCalculator(1, 1).calculate(candles)

    def test_invalid_extremes_are_rejected(self):
        candles = self._candles([10, 9, 12], [8, 7, 11])
        c = candles[1]
        candles[1] = Candle(c.symbol, c.timeframe_seconds, c.start, c.end,
                             c.open, 6, 7, c.close, c.volume, c.trade_count)
        with self.assertRaises(ValueError):
            StructureCalculator(1, 1).calculate(candles)


if __name__ == "__main__":
    unittest.main()
