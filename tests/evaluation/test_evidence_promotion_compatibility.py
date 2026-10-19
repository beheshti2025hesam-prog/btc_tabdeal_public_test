import unittest

from core.evaluation.canonicalization import canonicalize
from core.evaluation.final_promotion_gate import FinalPromotionGate
from core.evaluation.operational_safety import OperationalSafetyEvidence
from core.evaluation.producer import EvidenceResult
from core.evaluation.promotion_gate import PromotionEvidence
from core.evaluation.registry import EvidenceRegistry


PROJECT = "HES Trade Agent"
OWNER = "Seyed Hesameddin Beheshti Shirazi"
COMMIT = "abc123"


def complete_promotion_evidence() -> PromotionEvidence:
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


def safe_operational_evidence() -> OperationalSafetyEvidence:
    return OperationalSafetyEvidence(
        execution_disabled=True,
        venue_connection_disabled=True,
        capital_mutation_disabled=True,
        leverage_controlled=True,
        risk_veto_enforced=True,
        raw_data_immutable=True,
        audit_trail_available=True,
    )


class EvidencePromotionCompatibilityTests(unittest.TestCase):
    def test_full_producer_to_final_gate_path_is_eligible(self):
        canonical = canonicalize(
            [
                EvidenceResult("data_quality", True, "invalid_rows=0"),
                EvidenceResult("data_integrity", True, "clean"),
                EvidenceResult("coverage", True, "confirmed_coverage_gaps=0"),
            ],
            project_name=PROJECT,
            owner=OWNER,
            source_commit=COMMIT,
        )

        registry = EvidenceRegistry().append(canonical.snapshot)
        result = FinalPromotionGate().evaluate(
            complete_promotion_evidence(),
            canonical.snapshot,
            registry,
            safe_operational_evidence(),
            current_source_commit=COMMIT,
        )

        self.assertTrue(result.eligible)
        self.assertEqual(result.missing, ())

    def test_unregistered_snapshot_is_rejected(self):
        canonical = canonicalize(
            [],
            project_name=PROJECT,
            owner=OWNER,
            source_commit=COMMIT,
        )

        result = FinalPromotionGate().evaluate(
            complete_promotion_evidence(),
            canonical.snapshot,
            EvidenceRegistry(),
            safe_operational_evidence(),
            current_source_commit=COMMIT,
        )

        self.assertFalse(result.eligible)
        self.assertIn("snapshot_not_registered", result.missing)

    def test_stale_snapshot_is_rejected(self):
        canonical = canonicalize(
            [],
            project_name=PROJECT,
            owner=OWNER,
            source_commit=COMMIT,
        )
        registry = EvidenceRegistry().append(canonical.snapshot)

        result = FinalPromotionGate().evaluate(
            complete_promotion_evidence(),
            canonical.snapshot,
            registry,
            safe_operational_evidence(),
            current_source_commit="newer-commit",
        )

        self.assertFalse(result.eligible)
        self.assertIn("stale_source_commit", result.missing)

    def test_operational_safety_failure_blocks_final_gate(self):
        canonical = canonicalize(
            [],
            project_name=PROJECT,
            owner=OWNER,
            source_commit=COMMIT,
        )
        registry = EvidenceRegistry().append(canonical.snapshot)
        unsafe = OperationalSafetyEvidence(
            execution_disabled=False,
            venue_connection_disabled=True,
            capital_mutation_disabled=True,
            leverage_controlled=True,
            risk_veto_enforced=True,
            raw_data_immutable=True,
            audit_trail_available=True,
        )

        result = FinalPromotionGate().evaluate(
            complete_promotion_evidence(),
            canonical.snapshot,
            registry,
            unsafe,
            current_source_commit=COMMIT,
        )

        self.assertFalse(result.eligible)
        self.assertIn("operational_safety_unverified", result.missing)


if __name__ == "__main__":
    unittest.main()
