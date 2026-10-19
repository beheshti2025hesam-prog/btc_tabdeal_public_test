import unittest

from core.data_engine.quality import DataQualityReport
from core.evaluation.data_coverage_producer import CoverageEvidenceProducer


class CoverageEvidenceProducerTests(unittest.TestCase):
    def test_no_declared_or_confirmed_gap_passes(self):
        result = CoverageEvidenceProducer().produce(DataQualityReport(total_trades=10))
        self.assertTrue(result.passed)
        self.assertIn("declared_coverage_gaps=0", result.details)

    def test_declared_gap_without_confirmation_does_not_fail(self):
        report = DataQualityReport(
            total_trades=10,
            metadata={"declared_coverage_gaps": 2, "confirmed_coverage_gaps": 0},
        )
        result = CoverageEvidenceProducer().produce(report)
        self.assertTrue(result.passed)
        self.assertIn("sequence_gaps_are_not_confirmed_coverage_loss=true", result.details)

    def test_confirmed_gap_fails_closed(self):
        report = DataQualityReport(
            total_trades=10,
            metadata={"declared_coverage_gaps": 2, "confirmed_coverage_gaps": 1},
        )
        result = CoverageEvidenceProducer().produce(report)
        self.assertFalse(result.passed)
        self.assertIn("confirmed_coverage_gaps=1", result.details)

    def test_invalid_metadata_fails(self):
        with self.assertRaises(ValueError):
            CoverageEvidenceProducer().produce(
                DataQualityReport(
                    total_trades=10,
                    metadata={"declared_coverage_gaps": 0, "confirmed_coverage_gaps": 1},
                )
            )

    def test_wrong_context_rejected(self):
        with self.assertRaises(TypeError):
            CoverageEvidenceProducer().produce(object())


if __name__ == "__main__":
    unittest.main()
