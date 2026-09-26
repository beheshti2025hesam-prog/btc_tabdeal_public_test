"""Tests for the execution-free evidence aggregator."""

import unittest

from core.evaluation.aggregator import EvidenceAggregator
from core.evaluation.producer import EvidenceResult


class EvidenceAggregatorTests(unittest.TestCase):
    def test_builds_snapshot_from_results(self):
        snapshot = EvidenceAggregator().build(
            "commit-1",
            (
                EvidenceResult("oos", True),
                EvidenceResult("robustness", True),
            ),
        )
        self.assertEqual(snapshot.project_name, "HES Trade Agent")
        self.assertEqual(snapshot.owner, "Seyed Hesameddin Beheshti Shirazi")
        self.assertEqual(snapshot.source_commit, "commit-1")
        self.assertEqual(dict(snapshot.evidence), {"oos": True, "robustness": True})
        self.assertTrue(snapshot.verify())

    def test_preserves_failed_evidence(self):
        snapshot = EvidenceAggregator().build(
            "commit-1",
            (EvidenceResult("oos", True), EvidenceResult("robustness", False)),
        )
        self.assertEqual(dict(snapshot.evidence)["robustness"], False)

    def test_duplicate_gate_fails_closed(self):
        with self.assertRaises(ValueError):
            EvidenceAggregator().build(
                "commit-1",
                (EvidenceResult("oos", True), EvidenceResult("oos", False)),
            )

    def test_empty_results_fail_closed(self):
        with self.assertRaises(ValueError):
            EvidenceAggregator().build("commit-1", ())

    def test_empty_source_commit_fails_closed(self):
        with self.assertRaises(ValueError):
            EvidenceAggregator().build("", (EvidenceResult("oos", True),))


if __name__ == "__main__":
    unittest.main()
