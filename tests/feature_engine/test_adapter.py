"""Boundary tests for Data Intelligence -> Feature Engine adaptation."""
import unittest
from datetime import datetime, timedelta, timezone

from core.data_engine.candles import Candle
from core.data_engine.vwap import VWAPSnapshot
from core.feature_engine.adapter import (
    DataIntelligenceFeatureAdapter,
    IntelligenceFeatureInput,
)
from core.feature_engine.ema import EMASnapshot


class DataIntelligenceFeatureAdapterTests(unittest.TestCase):
    def setUp(self):
        self.start = datetime(2026, 9, 25, 10, 0, tzinfo=timezone.utc)
        self.end = self.start + timedelta(minutes=1)
        self.candle = Candle("BTC_USDT", 60, self.start, self.end, 100, 105, 99, 103, 12, 3)
        self.ema = EMASnapshot("BTC_USDT", 60, 20, self.end, 101)
        self.vwap = VWAPSnapshot("BTC_USDT", 60, self.start, self.end, 12, 102, 3)

    def item(self, **overrides):
        values = dict(candle=self.candle, ema=self.ema, vwap=self.vwap)
        values.update(overrides)
        return IntelligenceFeatureInput(**values)

    def test_builds_aligned_snapshot(self):
        snapshot = DataIntelligenceFeatureAdapter().build(self.item(buy_ratio=0.6))
        self.assertEqual(snapshot.symbol, "BTC_USDT")
        self.assertEqual(snapshot.timestamp, self.end)
        self.assertEqual(snapshot.ema, 101)
        self.assertEqual(snapshot.vwap, 102)
        self.assertEqual(snapshot.buy_ratio, 0.6)

    def test_rejects_symbol_mismatch(self):
        bad = EMASnapshot("ETH_USDT", 60, 20, self.end, 101)
        with self.assertRaises(ValueError):
            DataIntelligenceFeatureAdapter().build(self.item(ema=bad))

    def test_rejects_timeframe_mismatch(self):
        bad = EMASnapshot("BTC_USDT", 300, 20, self.end, 101)
        with self.assertRaises(ValueError):
            DataIntelligenceFeatureAdapter().build(self.item(ema=bad))

    def test_rejects_ema_timestamp_mismatch(self):
        bad = EMASnapshot("BTC_USDT", 60, 20, self.start, 101)
        with self.assertRaises(ValueError):
            DataIntelligenceFeatureAdapter().build(self.item(ema=bad))

    def test_rejects_vwap_window_mismatch(self):
        bad = VWAPSnapshot("BTC_USDT", 60, self.start + timedelta(seconds=60),
                           self.end + timedelta(seconds=60), 12, 102, 3)
        with self.assertRaises(ValueError):
            DataIntelligenceFeatureAdapter().build(self.item(vwap=bad))


if __name__ == "__main__":
    unittest.main()
