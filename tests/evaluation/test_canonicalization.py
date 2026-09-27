import unittest

from core.evaluation.canonicalization import canonicalize
from core.evaluation.evidence import EvidenceSnapshot
from core.evaluation.producer import EvidenceResult


PROJECT = "HES Trade Agent"
OWNER = "Seyed Hesameddin Beheshti Shirazi"
COMMIT = "abc123"


class EvidenceCanonicalizationTests(unittest.TestCase):
    def test_producer_results_map_to_canonical_snapshot(self):
        result = canonicalize(
            [
                EvidenceResult("data_quality", True, "invalid_rows=0"),
                EvidenceResult("coverage", False, "confirmed_coverage_gaps=1"),
            ],
            project_name=PROJECT,
            owner=OWNER,
            source_commit=COMMIT,
        )

        self.assertEqual(
            result.snapshot.evidence,
            (("coverage", False), ("data_quality", True)),
        )
        self.assertTrue(result.snapshot.verify())

    def test_identity_and_source_commit_are_preserved(self):
        result = canonicalize(
            [EvidenceResult("data_quality", True, "clean")],
            project_name=PROJECT,
            owner=OWNER,
            source_commit=COMMIT,
        )

        self.assertEqual(result.snapshot.project_name, PROJECT)
        self.assertEqual(result.snapshot.owner, OWNER)
        self.assertEqual(result.snapshot.source_commit, COMMIT)

    def test_details_are_retained_without_entering_canonical_digest(self):
        result = canonicalize(
            [EvidenceResult("data_quality", True, "invalid_rows=0")],
            project_name=PROJECT,
            owner=OWNER,
            source_commit=COMMIT,
        )

        self.assertEqual(result.details, (("data_quality", "invalid_rows=0"),))
        rebuilt = EvidenceSnapshot.create(PROJECT, OWNER, COMMIT, {"data_quality": True})
        self.assertEqual(result.snapshot.digest, rebuilt.digest)

    def test_duplicate_gate_names_fail_closed(self):
        with self.assertRaises(ValueError):
            canonicalize(
                [
                    EvidenceResult("coverage", True, "first"),
                    EvidenceResult("coverage", False, "second"),
                ],
                project_name=PROJECT,
                owner=OWNER,
                source_commit=COMMIT,
            )

    def test_non_producer_result_is_rejected(self):
        with self.assertRaises(TypeError):
            canonicalize(
                [object()],
                project_name=PROJECT,
                owner=OWNER,
                source_commit=COMMIT,
            )

    def test_empty_results_create_valid_empty_snapshot(self):
        result = canonicalize(
            [],
            project_name=PROJECT,
            owner=OWNER,
            source_commit=COMMIT,
        )

        self.assertEqual(result.snapshot.evidence, ())
        self.assertTrue(result.snapshot.verify())


if __name__ == "__main__":
    unittest.main()
