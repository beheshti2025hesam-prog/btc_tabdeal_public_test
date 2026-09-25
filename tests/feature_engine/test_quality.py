"""Feature Quality safety-boundary contract tests for HES Trade Agent."""
import unittest
from datetime import datetime, timezone

from core.feature_engine.quality import FeatureQualityGate, FeatureSnapshot


class FeatureQualityTests(unittest.TestCase):
    def _snapshot(self, **overrides):
        values = dict(
            symbol="BTC_USDT",
            timeframe_seconds=900,
            close=100.0,
            ema=100.0,
            vwap=100.0,
            buy_sell_delta=0.0,
            buy_ratio=0.5,
            realized_volatility=0.1,
            average_true_range=1.0,
            volume_ratio=1.0,
            volume_spike=False,
            regime="range",
            timestamp=datetime(2026, 9, 25, 10, 0, tzinfo=timezone.utc),
        )
        values.update(overrides)
        return FeatureSnapshot(**values)

    def test_complete_snapshot_passes(self):
        self.assertTrue(FeatureQualityGate().evaluate(self._snapshot()).passed)

    def test_missing_required_features_are_rejected(self):
        result = FeatureQualityGate().evaluate(self._snapshot(ema=None, vwap=None))
        self.assertFalse(result.passed)
        self.assertIn("missing_ema", result.violations)
        self.assertIn("missing_vwap", result.violations)

    def test_optional_requirements_can_be_disabled(self):
        result = FeatureQualityGate(require_ema=False, require_vwap=False).evaluate(
            self._snapshot(ema=None, vwap=None)
        )
        self.assertTrue(result.passed)

    def test_rejects_non_finite_and_non_positive_numeric_features(self):
        for value in (float("nan"), float("inf"), float("-inf"), 0.0, -1.0):
            result = FeatureQualityGate().evaluate(self._snapshot(close=value))
            self.assertFalse(result.passed)
            self.assertIn("invalid_close", result.violations)

    def test_rejects_invalid_optional_numeric_features(self):
        checks = (
            ("buy_ratio", 1.1, "invalid_buy_ratio"),
            ("volume_ratio", float("nan"), "invalid_volume_ratio"),
            ("realized_volatility", -1.0, "invalid_volatility"),
            ("average_true_range", float("inf"), "invalid_atr"),
            ("buy_sell_delta", float("nan"), "invalid_buy_sell_delta"),
        )
        for field, value, violation in checks:
            result = FeatureQualityGate().evaluate(self._snapshot(**{field: value}))
            self.assertFalse(result.passed)
            self.assertIn(violation, result.violations)

    def test_rejects_naive_timestamp(self):
        result = FeatureQualityGate().evaluate(
            self._snapshot(timestamp=datetime(2026, 9, 25, 10, 0))
        )
        self.assertFalse(result.passed)
        self.assertIn("invalid_timestamp", result.violations)

    def test_accepts_timezone_aware_timestamp(self):
        result = FeatureQualityGate().evaluate(self._snapshot())
        self.assertTrue(result.passed)


if __name__ == "__main__":
    unittest.main()
