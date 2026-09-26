"""End-to-end execution-free evidence flow test."""

import unittest

from core.evaluation.aggregator import EvidenceAggregator
from core.evaluation.producer import EvidenceResult
from core.evaluation.promotion import PromotionGate
from core.evaluation.registry import EvidenceRegistry
from core.evaluation.schema import EvidenceGate, EvidenceGateSchema


class EvidenceEndToEndTests(unittest.TestCase):
    def test_producer_aggregator_registry_schema_promotion_flow(self):
        source_commit = "commit-e2e-1"
        schema = EvidenceGateSchema(
            (
                EvidenceGate("oos", "Out-of-sample validation evidence."),
                EvidenceGate("robustness", "Fold stability evidence."),
            )
        )
        results = (
            EvidenceResult("oos", True, "validated"),
            EvidenceResult("robustness", True, "validated"),
        )

        snapshot = EvidenceAggregator().build(source_commit, results)
        registry = EvidenceRegistry().append(snapshot)
        result = PromotionGate().evaluate_registry(
            registry, source_commit, schema
        )

        self.assertTrue(result.eligible)
        self.assertEqual(result.reasons, ())
        self.assertEqual(registry.latest(), snapshot)
        self.assertTrue(snapshot.verify())

    def test_stale_registry_snapshot_blocks_flow(self):
        snapshot = EvidenceAggregator().build(
            "old-commit",
            (EvidenceResult("oos", True),),
        )
        registry = EvidenceRegistry().append(snapshot)
        schema = EvidenceGateSchema(
            (EvidenceGate("oos", "Out-of-sample validation evidence."),)
        )

        result = PromotionGate().evaluate_registry(
            registry, "new-commit", schema
        )

        self.assertFalse(result.eligible)
        self.assertIn("stale_source_commit", result.reasons)

    def test_failed_producer_evidence_blocks_flow(self):
        snapshot = EvidenceAggregator().build(
            "commit-e2e-2",
            (EvidenceResult("oos", False),),
        )
        registry = EvidenceRegistry().append(snapshot)
        schema = EvidenceGateSchema(
            (EvidenceGate("oos", "Out-of-sample validation evidence."),)
        )

        result = PromotionGate().evaluate_registry(
            registry, "commit-e2e-2", schema
        )

        self.assertFalse(result.eligible)
        self.assertIn("failed_evidence:oos", result.reasons)


if __name__ == "__main__":
    unittest.main()
