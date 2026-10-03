"""Tests for immutable evidence registry and stale detection."""

import unittest

from core.evaluation.evidence import EvidenceSnapshot
from core.evaluation.registry import EvidenceRegistry, EvidenceRegistryValidator


class EvidenceRegistryTests(unittest.TestCase):
    def snapshot(self, commit="abc123"):
        return EvidenceSnapshot.create(
            "HES Trade Agent",
            "Seyed Hesameddin Beheshti Shirazi",
            commit,
            {"oos": True, "paper": True},
        )

    def test_append_is_immutable(self):
        first = self.snapshot()
        registry = EvidenceRegistry().append(first)

        self.assertEqual(EvidenceRegistry().snapshots, ())
        self.assertEqual(registry.snapshots, (first,))
        self.assertIs(registry.latest(), first)

    def test_invalid_snapshot_cannot_be_registered(self):
        snapshot = self.snapshot()
        tampered = EvidenceSnapshot(
            snapshot.project_name,
            snapshot.owner,
            snapshot.source_commit,
            (("oos", False), ("paper", True)),
            snapshot.digest,
        )

        with self.assertRaisesRegex(ValueError, "invalid evidence snapshot"):
            EvidenceRegistry().append(tampered)

    def test_duplicate_snapshot_is_rejected(self):
        snapshot = self.snapshot()
        registry = EvidenceRegistry().append(snapshot)

        with self.assertRaisesRegex(ValueError, "duplicate evidence snapshot"):
            registry.append(snapshot)

    def test_current_commit_is_fresh(self):
        snapshot = self.snapshot("commit-1")
        result = EvidenceRegistryValidator().validate(snapshot, "commit-1")

        self.assertTrue(result.fresh)
        self.assertEqual(result.reasons, ())

    def test_changed_commit_makes_evidence_stale(self):
        snapshot = self.snapshot("commit-1")
        result = EvidenceRegistryValidator().validate(snapshot, "commit-2")

        self.assertFalse(result.fresh)
        self.assertIn("stale_source_commit", result.reasons)

    def test_identity_mismatch_is_rejected(self):
        snapshot = EvidenceSnapshot.create(
            "Wrong Project",
            "Wrong Owner",
            "commit-1",
            {"oos": True},
        )
        result = EvidenceRegistryValidator().validate(snapshot, "commit-1")

        self.assertFalse(result.fresh)
        self.assertIn("project_identity_mismatch", result.reasons)
        self.assertIn("owner_identity_mismatch", result.reasons)

    def test_empty_evidence_snapshot_is_invalid(self):
        snapshot = EvidenceSnapshot(
            "HES Trade Agent",
            "Seyed Hesameddin Beheshti Shirazi",
            "commit-1",
            (),
            "0" * 64,
        )
        self.assertFalse(snapshot.verify())

    def test_invalid_digest_is_rejected(self):
        snapshot = EvidenceSnapshot(
            "HES Trade Agent",
            "Seyed Hesameddin Beheshti Shirazi",
            "commit-1",
            (("oos", True),),
            "not-a-digest",
        )
        self.assertFalse(snapshot.verify())

    def test_non_boolean_evidence_is_invalid(self):
        snapshot = EvidenceSnapshot(
            "HES Trade Agent",
            "Seyed Hesameddin Beheshti Shirazi",
            "commit-1",
            (("oos", "true"),),
            "0" * 64,
        )
        self.assertFalse(snapshot.verify())

    def test_missing_source_commit_is_invalid(self):
        snapshot = EvidenceSnapshot(
            "HES Trade Agent",
            "Seyed Hesameddin Beheshti Shirazi",
            "",
            (("oos", True),),
            "0" * 64,
        )
        self.assertFalse(snapshot.verify())


if __name__ == "__main__":
    unittest.main()
