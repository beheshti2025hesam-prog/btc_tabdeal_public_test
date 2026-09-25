"""Tests for the final evidence-only promotion gate."""

import unittest

from core.evaluation.evidence import EvidenceSnapshot
from core.evaluation.final_promotion_gate import FinalPromotionGate
from core.evaluation.operational_safety import OperationalSafetyEvidence
from core.evaluation.promotion_gate import PromotionEvidence
from core.evaluation.registry import EvidenceRegistry


class FinalPromotionGateTests(unittest.TestCase):
    def evidence(self):
        return PromotionEvidence(
            data_quality_verified=True,
            historical_validation_verified=True,
            oos_walk_forward_verified=True,
            oos_stability_verified=True,
            paper_validation_verified=True,
            paper_performance_verified=True,
            paper_robustness_verified=True,
            risk_boundary_verified=True,
            live_safety_verified=True,
        )

    def safety(self):
        return OperationalSafetyEvidence(
            execution_disabled=True,
            venue_connection_disabled=True,
            capital_mutation_disabled=True,
            leverage_controlled=True,
            risk_veto_enforced=True,
            raw_data_immutable=True,
            audit_trail_available=True,
        )

    def test_all_verified_evidence_is_eligible(self):
        source_commit = "a" * 40
        snapshot = EvidenceSnapshot.create(
            project_name="HES Trade Agent",
            owner="Seyed Hesameddin Beheshti Shirazi",
            source_commit=source_commit,
            evidence=("all_verified",),
        )
        registry = EvidenceRegistry((snapshot,))
        result = FinalPromotionGate().evaluate(
            self.evidence(),
            snapshot,
            registry,
            self.safety(),
            current_source_commit=source_commit,
        )
        self.assertTrue(result.eligible)
        self.assertEqual(result.missing, ())

    def test_unverified_safety_blocks_eligibility(self):
        source_commit = "b" * 40
        snapshot = EvidenceSnapshot.create(
            project_name="HES Trade Agent",
            owner="Seyed Hesameddin Beheshti Shirazi",
            source_commit=source_commit,
            evidence=("all_verified",),
        )
        registry = EvidenceRegistry((snapshot,))
        safety = self.safety()
        unsafe = OperationalSafetyEvidence(
            safety.execution_disabled,
            safety.venue_connection_disabled,
            safety.capital_mutation_disabled,
            safety.leverage_controlled,
            False,
            safety.raw_data_immutable,
            safety.audit_trail_available,
        )
        result = FinalPromotionGate().evaluate(
            self.evidence(),
            snapshot,
            registry,
            unsafe,
            current_source_commit=source_commit,
        )
        self.assertFalse(result.eligible)
        self.assertIn("operational_safety_unverified", result.missing)


if __name__ == "__main__":
    unittest.main()
