import unittest

from core.data_engine.feature_engine import FeatureEngine


class FeatureEngineTests(unittest.TestCase):
    def test_builds_snapshot_from_partial_intelligence(self):
        snapshot = FeatureEngine().build(
            symbol="BTC_USDT",
            timeframe_seconds=900,
            close=100.0,
        )
        self.assertEqual(snapshot.symbol, "BTC_USDT")
        self.assertEqual(snapshot.timeframe_seconds, 900)
        self.assertEqual(snapshot.close, 100.0)
        self.assertIsNone(snapshot.ema)
        self.assertIsNone(snapshot.regime)


if __name__ == "__main__":
    unittest.main()


    def test_rejects_non_positive_timeframe(self):
        with self.assertRaises(ValueError):
            FeatureEngine().build(symbol="BTC_USDT", timeframe_seconds=0)

        with self.assertRaises(ValueError):
            FeatureEngine().build(symbol="BTC_USDT", timeframe_seconds=-900)

    def test_rejects_empty_symbol(self):
        with self.assertRaises(ValueError):
            FeatureEngine().build(symbol="", timeframe_seconds=900)

    def test_rejects_naive_timestamp(self):
        from datetime import datetime

        with self.assertRaises(ValueError):
            FeatureEngine().build(
                symbol="BTC_USDT",
                timeframe_seconds=900,
                timestamp=datetime(2026, 1, 1),
            )
