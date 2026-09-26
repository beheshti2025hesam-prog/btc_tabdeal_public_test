"""Tests for the generic evidence gate schema."""

import unittest

from core.evaluation.schema import EvidenceGate, EvidenceGateSchema


class EvidenceGateSchemaTests(unittest.TestCase):
    def test_schema_exposes_stable_required_names(self):
        schema = EvidenceGateSchema(
            (
                EvidenceGate("oos", "Out-of-sample validation evidence."),
                EvidenceGate("robustness", "Fold stability evidence."),
            )
        )
        self.assertEqual(schema.names, ("oos", "robustness"))
        self.assertEqual(schema.as_required_evidence(), ("oos", "robustness"))

    def test_empty_name_is_rejected(self):
        with self.assertRaises(ValueError):
            EvidenceGate("", "description")

    def test_empty_description_is_rejected(self):
        with self.assertRaises(ValueError):
            EvidenceGate("oos", " ")

    def test_empty_schema_is_rejected(self):
        with self.assertRaises(ValueError):
            EvidenceGateSchema(())

    def test_duplicate_names_are_rejected(self):
        with self.assertRaises(ValueError):
            EvidenceGateSchema(
                (
                    EvidenceGate("oos", "first"),
                    EvidenceGate("oos", "duplicate"),
                )
            )

    def test_schema_is_immutable(self):
        schema = EvidenceGateSchema(
            (EvidenceGate("oos", "Out-of-sample validation evidence."),)
        )
        with self.assertRaises(Exception):
            schema.gates = ()


if __name__ == "__main__":
    unittest.main()
