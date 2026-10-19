"""Tests for the execution-free evidence producer contract."""

import unittest

from core.evaluation.producer import EvidenceProducer, EvidenceResult


class StubProducer:
    gate_name = "oos"

    def produce(self, context):
        return EvidenceResult("oos", True, "validated")


class EvidenceProducerTests(unittest.TestCase):
    def test_result_is_immutable(self):
        result = EvidenceResult("oos", True)
        with self.assertRaises(Exception):
            result.passed = False

    def test_result_rejects_invalid_gate_name(self):
        with self.assertRaises(ValueError):
            EvidenceResult("", True)

    def test_result_rejects_non_boolean_status(self):
        with self.assertRaises(ValueError):
            EvidenceResult("oos", 1)

    def test_result_accepts_optional_details(self):
        result = EvidenceResult("oos", True, "validated")
        self.assertEqual(result.details, "validated")

    def test_producer_shape_is_structural(self):
        producer = StubProducer()
        self.assertEqual(producer.gate_name, "oos")
        result = producer.produce({"source_commit": "abc"})
        self.assertEqual(result.gate_name, "oos")
        self.assertTrue(result.passed)


if __name__ == "__main__":
    unittest.main()
