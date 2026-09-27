import unittest

from core.evaluation.evidence_bundle import EvidenceBundle
from core.evaluation.producer import EvidenceResult


class EvidenceBundleTests(unittest.TestCase):
    def test_builds_immutable_bundle(self):
        bundle = EvidenceBundle(
            "commit-1",
            (
                EvidenceResult("data_quality", True, "ok"),
                EvidenceResult("data_integrity", True, "ok"),
                EvidenceResult("coverage", True, "ok"),
            ),
        )
        self.assertEqual(bundle.source_commit, "commit-1")
        self.assertEqual(len(bundle.results), 3)

    def test_empty_commit_rejected(self):
        with self.assertRaises(ValueError):
            EvidenceBundle("", (EvidenceResult("x", True, "ok"),))

    def test_empty_results_rejected(self):
        with self.assertRaises(ValueError):
            EvidenceBundle("commit-1", ())

    def test_duplicate_gate_rejected(self):
        result = EvidenceResult("data_quality", True, "ok")
        with self.assertRaises(ValueError):
            EvidenceBundle("commit-1", (result, result))

    def test_bundle_is_frozen(self):
        bundle = EvidenceBundle("commit-1", (EvidenceResult("x", True, "ok"),))
        with self.assertRaises(Exception):
            bundle.source_commit = "other"


if __name__ == "__main__":
    unittest.main()
