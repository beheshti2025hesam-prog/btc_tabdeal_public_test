"""Support/resistance contract tests for HES Trade Agent."""
import unittest
from datetime import datetime, timedelta, timezone

from core.data_engine.candles import Candle
from core.feature_engine.support_resistance import SupportResistanceCalculator


class SupportResistanceTests(unittest.TestCase):
    def _candles(self):
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        values = [(100, 105), (102, 107), (99, 104), (101, 110)]
        return [
            Candle("BTC_USDT", 60, start + timedelta(minutes=i), start + timedelta(minutes=i + 1),
                   low, high, low, high, 1.0, 1)
            for i, (low, high) in enumerate(values)
        ]

    def test_rolling_levels_are_deterministic(self):
        result = SupportResistanceCalculator(3).calculate(self._candles())
        self.assertEqual(len(result), 2)
        self.assertEqual((result[0].support, result[0].resistance), (99, 107))
        self.assertEqual((result[1].support, result[1].resistance), (99, 110))

    def test_insufficient_history_produces_no_snapshot(self):
        self.assertEqual(SupportResistanceCalculator(5).calculate(self._candles()), [])

    def test_invalid_lookback_is_rejected(self):
        with self.assertRaises(ValueError):
            SupportResistanceCalculator(0)

    def test_naive_timestamp_is_rejected(self):
        candles = self._candles()
        c = candles[0]
        candles[0] = Candle(c.symbol, c.timeframe_seconds, c.start.replace(tzinfo=None), c.end,
                             c.open, c.high, c.low, c.close, c.volume, c.trade_count)
        with self.assertRaises(ValueError):
            SupportResistanceCalculator(1).calculate(candles)

    def test_invalid_extremes_are_rejected(self):
        candles = self._candles()
        c = candles[0]
        candles[0] = Candle(c.symbol, c.timeframe_seconds, c.start, c.end,
                             c.open, 90, 100, c.close, c.volume, c.trade_count)
        with self.assertRaises(ValueError):
            SupportResistanceCalculator(1).calculate(candles)


if __name__ == "__main__":
    unittest.main()
