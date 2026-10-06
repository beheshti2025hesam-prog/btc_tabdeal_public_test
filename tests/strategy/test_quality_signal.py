"""Tests for the POST-QUALITY-BASELINE v2 signal gate."""
import unittest

from core.strategy.quality_signal import (
    PostQualityBaselineV2,
    QualityDecision,
    QualitySignalInput,
)


class QualitySignalTests(unittest.TestCase):
    def base(self, **overrides):
        values = dict(
            data_valid=True,
            direction="long",
            htf_trend="long",
            htf_alignment=True,
            structure_bias="long",
            structure_break_confirmed=True,
            location_valid=True,
            liquidity_event_confirmed=True,
            entry_trigger_confirmed=True,
            displacement_confirmed=True,
            momentum_confirmed=True,
            participation_confirmed=False,
            contradiction=False,
            stop_valid=True,
            rr=3.0,
        )
        values.update(overrides)
        return QualitySignalInput(**values)

    def test_clean_long_passes(self):
        result = PostQualityBaselineV2().evaluate(self.base())
        self.assertEqual(result.decision, QualityDecision.LONG)
        self.assertEqual(result.reasons, ())

    def test_clean_short_passes(self):
        result = PostQualityBaselineV2().evaluate(
            self.base(direction="short", htf_trend="short", structure_bias="short")
        )
        self.assertEqual(result.decision, QualityDecision.SHORT)

    def test_correlated_indicators_are_not_enough(self):
        result = PostQualityBaselineV2().evaluate(
            self.base(
                structure_bias=None,
                structure_break_confirmed=None,
                location_valid=None,
                liquidity_event_confirmed=None,
                entry_trigger_confirmed=None,
                displacement_confirmed=None,
            )
        )
        self.assertEqual(result.decision, QualityDecision.NO_TRADE)

    def test_missing_evidence_is_not_a_neutral_vote(self):
        result = PostQualityBaselineV2().evaluate(
            self.base(momentum_confirmed=None, participation_confirmed=None)
        )
        self.assertEqual(result.decision, QualityDecision.NO_TRADE)
        self.assertIn("independent_confirmation_missing", result.reasons)

    def test_contradiction_is_hard_veto(self):
        result = PostQualityBaselineV2().evaluate(self.base(contradiction=True))
        self.assertEqual(result.decision, QualityDecision.NO_TRADE)
        self.assertIn("contradiction_or_unknown", result.reasons)

    def test_rr_gate_is_hard_veto(self):
        result = PostQualityBaselineV2().evaluate(self.base(rr=2.99))
        self.assertEqual(result.decision, QualityDecision.NO_TRADE)
        self.assertIn("rr_below_minimum", result.reasons)

    def test_unknown_risk_is_no_trade(self):
        result = PostQualityBaselineV2().evaluate(self.base(stop_valid=None))
        self.assertEqual(result.decision, QualityDecision.NO_TRADE)

    def test_deterministic(self):
        strategy = PostQualityBaselineV2()
        data = self.base()
        self.assertEqual(strategy.evaluate(data), strategy.evaluate(data))


if __name__ == "__main__":
    unittest.main()
