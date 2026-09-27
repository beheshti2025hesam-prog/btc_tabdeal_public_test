import unittest

from core.data_engine.quality import DataQualityReport
from core.evaluation.canonicalization import canonicalize
from core.evaluation.data_coverage_producer import CoverageEvidenceProducer
from core.evaluation.data_integrity_producer import IntegrityEvidenceProducer
from core.evaluation.data_quality_producer import DataQualityEvidenceProducer
from core.evaluation.final_promotion_gate import FinalPromotionGate
from core.evaluation.operational_safety import OperationalSafetyEvidence
from core.evaluation.promotion_gate import PromotionEvidence
from core.evaluation.registry import EvidenceRegistry

PROJECT = "HES Trade Agent"
OWNER = "Seyed Hesameddin Beheshti Shirazi"
COMMIT = "abc123"


def complete_promotion_evidence() -> PromotionEvidence:
    return PromotionEvidence(True, True, True, True, True, True, True, True, True)


def safe_operational_evidence() -> OperationalSafetyEvidence:
    return OperationalSafetyEvidence(True, True, True, True, True, True, True)


class EvidencePromotionCompatibilityTests(unittest.TestCase):
    def test_real_producers_to_final_gate_path(self):
        report = DataQualityReport(
            total_trades=100,
            validation={"invalid_rows": 0},
            integrity={("tabdeal", "BTC_USDT"): {
                "duplicate_event_id_count": 0, "duplicate_sequence_count": 0,
                "sequence_gap_count": 0, "backward_sequence_count": 0,
                "timestamp_backward_count": 0}},
            metadata={"declared_coverage_gaps": 0, "confirmed_coverage_gaps": 0},
        )
        results = (
            DataQualityEvidenceProducer().produce(report),
            IntegrityEvidenceProducer().produce(report),
            CoverageEvidenceProducer().produce(report),
        )
        canonical = canonicalize(results, project_name=PROJECT, owner=OWNER, source_commit=COMMIT)
        registry = EvidenceRegistry().append(canonical.snapshot)
        result = FinalPromotionGate().evaluate(complete_promotion_evidence(), canonical.snapshot,
                                                registry, safe_operational_evidence(),
                                                current_source_commit=COMMIT)
        self.assertTrue(result.eligible)
        self.assertEqual(result.missing, ())

    def test_unregistered_snapshot_is_rejected(self):
        canonical = canonicalize([], project_name=PROJECT, owner=OWNER, source_commit=COMMIT)
        result = FinalPromotionGate().evaluate(complete_promotion_evidence(), canonical.snapshot,
                                                EvidenceRegistry(), safe_operational_evidence(),
                                                current_source_commit=COMMIT)
        self.assertFalse(result.eligible)
        self.assertIn("snapshot_not_registered", result.missing)

    def test_stale_snapshot_is_rejected(self):
        canonical = canonicalize([], project_name=PROJECT, owner=OWNER, source_commit=COMMIT)
        registry = EvidenceRegistry().append(canonical.snapshot)
        result = FinalPromotionGate().evaluate(complete_promotion_evidence(), canonical.snapshot,
                                                registry, safe_operational_evidence(),
                                                current_source_commit="newer-commit")
        self.assertFalse(result.eligible)
        self.assertIn("stale_source_commit", result.missing)

    def test_operational_safety_failure_blocks_final_gate(self):
        canonical = canonicalize([], project_name=PROJECT, owner=OWNER, source_commit=COMMIT)
        registry = EvidenceRegistry().append(canonical.snapshot)
        unsafe = OperationalSafetyEvidence(False, True, True, True, True, True, True)
        result = FinalPromotionGate().evaluate(complete_promotion_evidence(), canonical.snapshot,
                                                registry, unsafe, current_source_commit=COMMIT)
        self.assertFalse(result.eligible)
        self.assertIn("operational_safety_unverified", result.missing)


if __name__ == "__main__":
    unittest.main()
