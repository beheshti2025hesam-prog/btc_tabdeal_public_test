"""Deterministic price/VWAP relationship contract tests for HES Trade Agent."""
import unittest
from datetime import datetime, timedelta, timezone

from core.data_engine.candles import Candle
from core.data_engine.vwap import VWAPSnapshot
from core.feature_engine.price_vwap import PriceVWAPRelationshipCalculator


class PriceVWAPRelationshipTests(unittest.TestCase):
    def _window(self, minute=0):
        start = datetime(2026, 1, 1, 0, minute, tzinfo=timezone.utc)
        return start, start + timedelta(minutes=1)

    def _candle(self, close, minute=0):
        start, end = self._window(minute)
        return Candle("BTC_USDT", 60, start, end, close, close, close, close, 1.0, 1)

    def _vwap(self, value, minute=0):
        start, end = self._window(minute)
        return VWAPSnapshot("BTC_USDT", 60, start, end, 1.0, value, 1)

    def test_relationship_is_window_matched_and_deterministic(self):
        candles = [self._candle(101.0, 0), self._candle(99.0, 1)]
        vwaps = [self._vwap(100.0, 0), self._vwap(100.0, 1)]
        result = PriceVWAPRelationshipCalculator().calculate(candles, vwaps)

        self.assertEqual(len(result), 2)
        self.assertEqual(result[0].relation, "above")
        self.assertAlmostEqual(result[0].distance, 1.0)
        self.assertAlmostEqual(result[0].distance_pct, 0.01)
        self.assertEqual(result[1].relation, "below")
        self.assertAlmostEqual(result[1].distance_pct, -0.01)

    def test_at_vwap_is_explicit(self):
        result = PriceVWAPRelationshipCalculator().calculate(
            [self._candle(100.0)],
            [self._vwap(100.0)],
        )
        self.assertEqual(result[0].relation, "at_vwap")
        self.assertEqual(result[0].distance, 0.0)

    def test_unmatched_windows_are_not_invented(self):
        result = PriceVWAPRelationshipCalculator().calculate(
            [self._candle(101.0, 0)],
            [self._vwap(100.0, 1)],
        )
        self.assertEqual(result, [])

    def test_naive_timestamps_are_rejected(self):
        candle = self._candle(101.0)
        candle = Candle(
            candle.symbol, candle.timeframe_seconds,
            candle.start.replace(tzinfo=None), candle.end,
            candle.open, candle.high, candle.low, candle.close,
            candle.volume, candle.trade_count,
        )
        with self.assertRaises(ValueError):
            PriceVWAPRelationshipCalculator().calculate([candle], [self._vwap(100.0)])

    def test_duplicate_vwap_window_is_rejected(self):
        with self.assertRaises(ValueError):
            PriceVWAPRelationshipCalculator().calculate(
                [self._candle(101.0)],
                [self._vwap(100.0), self._vwap(101.0)],
            )


if __name__ == "__main__":
    unittest.main()
