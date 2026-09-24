import unittest

from core.data_engine.feature_engine import FeatureEngine
from core.data_engine.multitimeframe import MultiTimeframeFeatureEngine


class MultiTimeframeFeatureTests(unittest.TestCase):
    def setUp(self):
        self.engine = FeatureEngine()
        self.mtf = MultiTimeframeFeatureEngine()

    def test_snapshots_are_sorted_by_timeframe(self):
        slow = self.engine.build(symbol="BTC_USDT", timeframe_seconds=3600)
        fast = self.engine.build(symbol="BTC_USDT", timeframe_seconds=900)
        result = self.mtf.build([slow, fast])
        self.assertEqual(result.timeframes, (900, 3600))

    def test_mixed_symbols_are_rejected(self):
        a = self.engine.build(symbol="BTC_USDT", timeframe_seconds=900)
        b = self.engine.build(symbol="ETH_USDT", timeframe_seconds=3600)
        with self.assertRaises(ValueError):
            self.mtf.build([a, b])

    def test_duplicate_timeframe_is_rejected(self):
        a = self.engine.build(symbol="BTC_USDT", timeframe_seconds=900)
        b = self.engine.build(symbol="BTC_USDT", timeframe_seconds=900)
        with self.assertRaises(ValueError):
            self.mtf.build([a, b])


if __name__ == "__main__":
    unittest.main()
