"""Tests for the execution-free promotion evidence gate."""
import unittest

from core.evaluation.promotion_gate import PromotionEvidence, PromotionGate


class PromotionGateTests(unittest.TestCase):
    def base(self, **overrides):
        values = dict(
            data_quality_verified=True,
            historical_validation_verified=True,
            oos_walk_forward_verified=True,
            oos_stability_verified=True,
            paper_validation_verified=True,
            paper_performance_verified=True,
            paper_robustness_verified=True,
            risk_boundary_verified=True,
            live_safety_verified=False,
        )
        values.update(overrides)
        return PromotionEvidence(**values)

    def test_missing_live_safety_blocks_eligibility(self):
        result = PromotionGate().evaluate(self.base())
        self.assertFalse(result.eligible)
        self.assertEqual(result.missing, ("live_safety_verified",))

    def test_complete_evidence_is_eligible(self):
        result = PromotionGate().evaluate(self.base(live_safety_verified=True))
        self.assertTrue(result.eligible)
        self.assertEqual(result.missing, ())

    def test_reports_all_missing_evidence(self):
        result = PromotionGate().evaluate(
            self.base(
                data_quality_verified=False,
                paper_robustness_verified=False,
                risk_boundary_verified=False,
            )
        )
        self.assertFalse(result.eligible)
        self.assertIn("data_quality_verified", result.missing)
        self.assertIn("paper_robustness_verified", result.missing)
        self.assertIn("risk_boundary_verified", result.missing)


if __name__ == "__main__":
    unittest.main()
