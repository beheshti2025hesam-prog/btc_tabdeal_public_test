"""Tests for the execution-free Data Quality evidence producer."""

import unittest

from core.data_engine.quality import DataQualityReport
from core.evaluation.data_quality_producer import DataQualityEvidenceProducer


class DataQualityEvidenceProducerTests(unittest.TestCase):
    def test_clean_report_produces_passing_evidence(self):
        report = DataQualityReport(
            total_trades=10,
            validation={"invalid_rows": 0},
            integrity={},
        )
        result = DataQualityEvidenceProducer().produce(report)
        self.assertEqual(result.gate_name, "data_quality")
        self.assertTrue(result.passed)
        self.assertIn("invalid_rows=0", result.details)

    def test_invalid_rows_fail_evidence(self):
        report = DataQualityReport(
            total_trades=10,
            validation={"invalid_rows": 2},
            integrity={},
        )
        result = DataQualityEvidenceProducer().produce(report)
        self.assertFalse(result.passed)

    def test_integrity_issues_fail_evidence(self):
        report = DataQualityReport(
            total_trades=10,
            validation={"invalid_rows": 0},
            integrity={
                ("tabdeal", "BTC_USDT"): {"sequence_gap_count": 1}
            },
        )
        result = DataQualityEvidenceProducer().produce(report)
        self.assertFalse(result.passed)

    def test_invalid_context_fails_closed(self):
        with self.assertRaises(TypeError):
            DataQualityEvidenceProducer().produce(object())


if __name__ == "__main__":
    unittest.main()
