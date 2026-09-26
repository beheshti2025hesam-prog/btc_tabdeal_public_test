import unittest

from core.data_engine.quality import DataQualityReport
from core.evaluation.data_integrity_producer import IntegrityEvidenceProducer


class IntegrityEvidenceProducerTests(unittest.TestCase):
    def test_healthy_report_passes(self):
        report = DataQualityReport(
            total_trades=100,
            integrity={
                ("tabdeal", "BTC_USDT"): {
                    "duplicate_event_id_count": 0,
                    "duplicate_sequence_count": 0,
                    "sequence_gap_count": 0,
                    "backward_sequence_count": 0,
                    "timestamp_backward_count": 0,
                }
            },
        )
        result = IntegrityEvidenceProducer().produce(report)
        self.assertEqual(result.gate_name, "data_integrity")
        self.assertTrue(result.passed)
        self.assertIn("sequence_gaps=0", result.details)

    def test_any_integrity_issue_fails_closed(self):
        report = DataQualityReport(
            total_trades=100,
            integrity={
                ("tabdeal", "BTC_USDT"): {
                    "duplicate_event_id_count": 0,
                    "duplicate_sequence_count": 1,
                    "sequence_gap_count": 0,
                    "backward_sequence_count": 0,
                    "timestamp_backward_count": 0,
                }
            },
        )
        result = IntegrityEvidenceProducer().produce(report)
        self.assertFalse(result.passed)
        self.assertIn("duplicate_sequences=1", result.details)

    def test_multiple_groups_are_aggregated(self):
        report = DataQualityReport(
            total_trades=200,
            integrity={
                ("tabdeal", "BTC_USDT"): {"sequence_gap_count": 2},
                ("tabdeal", "ETH_USDT"): {"timestamp_backward_count": 1},
            },
        )
        result = IntegrityEvidenceProducer().produce(report)
        self.assertFalse(result.passed)
        self.assertIn("sequence_gaps=2", result.details)
        self.assertIn("timestamp_backward=1", result.details)

    def test_rejects_wrong_context(self):
        with self.assertRaises(TypeError):
            IntegrityEvidenceProducer().produce(object())


if __name__ == "__main__":
    unittest.main()
