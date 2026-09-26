"""Tests for Evidence Registry result consumption."""

import unittest

from core.evaluation.evidence import EvidenceSnapshot
from core.evaluation.producer import EvidenceResult
from core.evaluation.registry import EvidenceRegistry


class EvidenceRegistryResultTests(unittest.TestCase):
    def snapshot(self):
        return EvidenceSnapshot.create(
            "HES Trade Agent",
            "Seyed Hesameddin Beheshti Shirazi",
            "commit-1",
            {"oos": True},
        )

    def test_append_result_creates_new_snapshot(self):
        original = self.snapshot()
        registry = EvidenceRegistry().append_result(
            original, EvidenceResult("robustness", True, "validated")
        )
        latest = registry.latest()
        self.assertIsNotNone(latest)
        self.assertEqual(dict(latest.evidence), {"oos": True, "robustness": True})
        self.assertEqual(dict(original.evidence), {"oos": True})

    def test_append_result_preserves_identity_and_commit(self):
        original = self.snapshot()
        latest = EvidenceRegistry().append_result(
            original, EvidenceResult("robustness", False)
        ).latest()
        self.assertEqual(latest.project_name, original.project_name)
        self.assertEqual(latest.owner, original.owner)
        self.assertEqual(latest.source_commit, original.source_commit)
        self.assertTrue(latest.verify())

    def test_duplicate_gate_fails_closed(self):
        with self.assertRaises(ValueError):
            EvidenceRegistry().append_result(
                self.snapshot(), EvidenceResult("oos", False)
            )

    def test_invalid_result_gate_name_fails_closed(self):
        with self.assertRaises(ValueError):
            EvidenceRegistry().append_result(
                self.snapshot(), EvidenceResult(" ", True)
            )


if __name__ == "__main__":
    unittest.main()
