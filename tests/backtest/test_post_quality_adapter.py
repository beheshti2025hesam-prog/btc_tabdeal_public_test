"""Safety tests for the POST-QUALITY historical adapter."""
import unittest
from datetime import datetime, timezone

from core.backtest.post_quality_real_data import (
    PostQualityHistoricalAdapter,
    PostQualityObservation,
)
from core.strategy.quality_signal import QualityDecision


class PostQualityAdapterTests(unittest.TestCase):
    def test_incomplete_legacy_features_cannot_create_signal(self):
        obs = PostQualityObservation(
            timestamp=datetime(2026, 10, 6, tzinfo=timezone.utc),
            direction="long",
            htf_trend="long",
            htf_alignment=True,
            structure_bias=None,
            structure_break_confirmed=None,
            location_valid=None,
            liquidity_event_confirmed=None,
            entry_trigger_confirmed=None,
            displacement_confirmed=None,
            momentum_confirmed=True,
            participation_confirmed=False,
            contradiction=False,
            stop_valid=True,
            rr=3.0,
        )
        result = PostQualityHistoricalAdapter().evaluate(obs)
        self.assertEqual(result.decision, QualityDecision.NO_TRADE)
        self.assertIn("structure_bias_mismatch", result.reasons)

    def test_complete_evidence_can_pass(self):
        obs = PostQualityObservation(
            timestamp=datetime(2026, 10, 6, tzinfo=timezone.utc),
            direction="short",
            htf_trend="short",
            htf_alignment=True,
            structure_bias="short",
            structure_break_confirmed=True,
            location_valid=True,
            liquidity_event_confirmed=True,
            entry_trigger_confirmed=True,
            displacement_confirmed=True,
            momentum_confirmed=False,
            participation_confirmed=True,
            contradiction=False,
            stop_valid=True,
            rr=3.2,
        )
        result = PostQualityHistoricalAdapter().evaluate(obs)
        self.assertEqual(result.decision, QualityDecision.SHORT)
        self.assertEqual(result.reasons, ())


if __name__ == "__main__":
    unittest.main()
