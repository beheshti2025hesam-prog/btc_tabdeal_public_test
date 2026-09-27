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


    def test_data_quality_producer_flows_into_registry_and_promotion(self):
        from core.data_engine.quality import DataQualityReport
        from core.evaluation.data_quality_producer import DataQualityEvidenceProducer

        source_commit = "commit-real-quality-1"
        schema = EvidenceGateSchema(
            (EvidenceGate("data_quality", "Data Foundation quality evidence."),)
        )
        report = DataQualityReport(
            total_trades=100,
            validation={"invalid_rows": 0},
            integrity={},
        )
        evidence = DataQualityEvidenceProducer().produce(report)
        snapshot = EvidenceAggregator().build(source_commit, (evidence,))
        registry = EvidenceRegistry().append(snapshot)

        result = PromotionGate().evaluate_registry(
            registry, source_commit, schema
        )

        self.assertTrue(result.eligible)
        self.assertEqual(result.reasons, ())
        self.assertIn(("data_quality", True), registry.latest().evidence)
        self.assertTrue(registry.latest().verify())

    def test_three_data_foundation_evidence_bundle_flows_to_promotion(self):
        from core.evaluation.evidence_bundle import EvidenceBundle
        from core.evaluation.data_quality_producer import DataQualityEvidenceProducer
        from core.evaluation.data_integrity_producer import IntegrityEvidenceProducer
        from core.evaluation.data_coverage_producer import CoverageEvidenceProducer
        from core.data_engine.quality import DataQualityReport

        source_commit = "commit-data-foundation-e2e-1"
        report = DataQualityReport(
            total_trades=100,
            validation={"invalid_rows": 0},
            integrity={
                ("tabdeal", "BTC_USDT"): {
                    "duplicate_event_id_count": 0,
                    "duplicate_sequence_count": 0,
                    "sequence_gap_count": 0,
                    "backward_sequence_count": 0,
                    "timestamp_backward_count": 0,
                }
            },
            metadata={"declared_coverage_gaps": 0, "confirmed_coverage_gaps": 0},
        )
        results = (
            DataQualityEvidenceProducer().produce(report),
            IntegrityEvidenceProducer().produce(report),
            CoverageEvidenceProducer().produce(report),
        )
        bundle = EvidenceBundle(source_commit, results)
        snapshot = EvidenceAggregator().build(bundle.source_commit, bundle.results)
        registry = EvidenceRegistry().append(snapshot)
        schema = EvidenceGateSchema(
            (
                EvidenceGate("data_quality", "Data Foundation quality evidence."),
                EvidenceGate("data_integrity", "Data Foundation integrity evidence."),
                EvidenceGate("coverage", "Data coverage evidence."),
            )
        )
        result = PromotionGate().evaluate_registry(registry, source_commit, schema)
        self.assertTrue(result.eligible)
        self.assertEqual(result.reasons, ())
        self.assertEqual(
            dict(registry.latest().evidence),
            {"data_quality": True, "data_integrity": True, "coverage": True},
        )
        self.assertTrue(registry.latest().verify())

    def test_failed_integrity_or_coverage_blocks_three_gate_flow(self):
        from core.evaluation.evidence_bundle import EvidenceBundle
        from core.evaluation.data_quality_producer import DataQualityEvidenceProducer
        from core.evaluation.data_integrity_producer import IntegrityEvidenceProducer
        from core.evaluation.data_coverage_producer import CoverageEvidenceProducer
        from core.data_engine.quality import DataQualityReport

        source_commit = "commit-data-foundation-e2e-2"
        report = DataQualityReport(
            total_trades=100,
            validation={"invalid_rows": 0},
            integrity={
                ("tabdeal", "BTC_USDT"): {
                    "duplicate_event_id_count": 0,
                    "duplicate_sequence_count": 1,
                    "sequence_gap_count": 0,
                    "backward_sequence_count": 0,
                    "timestamp_backward_count": 0,
                }
            },
            metadata={"declared_coverage_gaps": 1, "confirmed_coverage_gaps": 1},
        )
        results = (
            DataQualityEvidenceProducer().produce(report),
            IntegrityEvidenceProducer().produce(report),
            CoverageEvidenceProducer().produce(report),
        )
        bundle = EvidenceBundle(source_commit, results)
        snapshot = EvidenceAggregator().build(bundle.source_commit, bundle.results)
        registry = EvidenceRegistry().append(snapshot)
        schema = EvidenceGateSchema(
            (
                EvidenceGate("data_quality", "Data Foundation quality evidence."),
                EvidenceGate("data_integrity", "Data Foundation integrity evidence."),
                EvidenceGate("coverage", "Data coverage evidence."),
            )
        )
        result = PromotionGate().evaluate_registry(registry, source_commit, schema)
        self.assertFalse(result.eligible)
        self.assertIn("failed_evidence:data_integrity", result.reasons)
        self.assertIn("failed_evidence:coverage", result.reasons)


if __name__ == "__main__":
    unittest.main()
