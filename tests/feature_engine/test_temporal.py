"""Boundary tests for the Feature Engine temporal alignment contract."""
import unittest
from datetime import datetime, timedelta, timezone

from core.feature_engine.temporal import FeatureTemporalAlignment, FeatureTemporalInput


class FeatureTemporalAlignmentTests(unittest.TestCase):
    def setUp(self):
        self.start = datetime(2026, 9, 25, 10, 0, tzinfo=timezone.utc)
        self.end = self.start + timedelta(minutes=1)

    def item(self, **overrides):
        values = dict(
            symbol="BTC_USDT",
            timeframe_seconds=60,
            window_start=self.start,
            window_end=self.end,
            feature_timestamp=self.end,
            source="data_intelligence",
            source_timestamp=self.end,
        )
        values.update(overrides)
        return FeatureTemporalInput(**values)

    def test_accepts_aligned_input(self):
        self.assertEqual(FeatureTemporalAlignment().validate(self.item()), ())

    def test_rejects_window_duration_mismatch(self):
        result = FeatureTemporalAlignment().validate(
            self.item(timeframe_seconds=900)
        )
        self.assertIn("window_duration_mismatch", result)

    def test_rejects_feature_timestamp_not_at_window_end(self):
        result = FeatureTemporalAlignment().validate(
            self.item(feature_timestamp=self.start)
        )
        self.assertIn("feature_timestamp_mismatch", result)

    def test_rejects_source_timestamp_in_future(self):
        result = FeatureTemporalAlignment().validate(
            self.item(source_timestamp=self.end + timedelta(seconds=1))
        )
        self.assertIn("source_timestamp_in_future", result)

    def test_rejects_naive_temporal_metadata(self):
        result = FeatureTemporalAlignment().validate(
            self.item(window_start=self.start.replace(tzinfo=None))
        )
        self.assertIn("invalid_window_start", result)

    def test_rejects_missing_provenance(self):
        result = FeatureTemporalAlignment().validate(self.item(source=""))
        self.assertIn("missing_source", result)


if __name__ == "__main__":
    unittest.main()
