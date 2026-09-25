import unittest
from datetime import datetime, timezone

from core.data_engine.feature_engine import FeatureSnapshot
from core.data_engine.feature_quality import FeatureQualityGate


class FeatureQualityTimestampTests(unittest.TestCase):
    def _snapshot(self, timestamp):
        return FeatureSnapshot(
            symbol="BTC_USDT",
            timeframe_seconds=900,
            close=100.0,
            ema=100.0,
            vwap=100.0,
            buy_sell_delta=None,
            buy_ratio=0.5,
            realized_volatility=0.1,
            average_true_range=1.0,
            volume_ratio=1.0,
            volume_spike=False,
            regime="range",
            timestamp=timestamp,
        )

    def test_rejects_naive_timestamp(self):
        result = FeatureQualityGate().evaluate(
            self._snapshot(datetime(2026, 9, 25, 10, 0, 0))
        )
        self.assertFalse(result.passed)
        self.assertIn("invalid_timestamp", result.violations)

    def test_accepts_timezone_aware_timestamp(self):
        result = FeatureQualityGate().evaluate(
            self._snapshot(
                datetime(2026, 9, 25, 10, 0, 0, tzinfo=timezone.utc)
            )
        )
        self.assertTrue(result.passed)


if __name__ == "__main__":
    unittest.main()
