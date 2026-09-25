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

    def test_rejects_non_finite_and_non_positive_numeric_features(self):
        from core.data_engine.feature_engine import FeatureSnapshot

        gate = FeatureQualityGate()
        for value in (float("nan"), float("inf"), float("-inf"), 0.0, -1.0):
            snapshot = FeatureSnapshot(
                symbol="BTC_USDT",
                timeframe_seconds=900,
                close=value,
                ema=100.0,
                vwap=100.0,
                buy_sell_delta=None,
                buy_ratio=0.5,
                realized_volatility=0.1,
                average_true_range=1.0,
                volume_ratio=1.0,
                volume_spike=False,
                regime="range",
            )
            result = gate.evaluate(snapshot)
            self.assertFalse(result.passed)
            self.assertIn("invalid_close", result.violations)


if __name__ == "__main__":
    unittest.main()
