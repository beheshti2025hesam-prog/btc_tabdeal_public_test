import unittest

from core.data_engine.feature_engine import FeatureEngine
from core.data_engine.feature_quality import FeatureQualityGate


class FeatureQualityTests(unittest.TestCase):
    def test_incomplete_snapshot_is_rejected(self):
        snapshot = FeatureEngine().build(
            symbol="BTC_USDT", timeframe_seconds=900, close=100
        )
        result = FeatureQualityGate().evaluate(snapshot)
        self.assertFalse(result.passed)
        self.assertIn("missing_ema", result.violations)
        self.assertIn("missing_vwap", result.violations)

    def test_optional_requirements_can_be_disabled(self):
        snapshot = FeatureEngine().build(
            symbol="BTC_USDT", timeframe_seconds=900, close=100
        )
        result = FeatureQualityGate(require_ema=False, require_vwap=False).evaluate(snapshot)
        self.assertTrue(result.passed)


if __name__ == "__main__":
    unittest.main()
