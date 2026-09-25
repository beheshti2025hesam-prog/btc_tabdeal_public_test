"""Tests for immutable promotion evidence snapshots."""
import unittest

from core.evaluation.evidence import EvidenceSnapshot


class EvidenceSnapshotTests(unittest.TestCase):
    def test_snapshot_is_self_verifying(self):
        snapshot = EvidenceSnapshot.create(
            "HES Trade Agent",
            "Seyed Hesameddin Beheshti Shirazi",
            "abc123",
            {"oos": True, "paper": True},
        )
        self.assertTrue(snapshot.verify())
        self.assertEqual(len(snapshot.digest), 64)

    def test_tampering_invalidates_digest(self):
        snapshot = EvidenceSnapshot.create(
            "HES Trade Agent",
            "Seyed Hesameddin Beheshti Shirazi",
            "abc123",
            {"oos": True},
        )
        tampered = EvidenceSnapshot(
            snapshot.project_name,
            snapshot.owner,
            snapshot.source_commit,
            (("oos", False),),
            snapshot.digest,
        )
        self.assertFalse(tampered.verify())


if __name__ == "__main__":
    unittest.main()
