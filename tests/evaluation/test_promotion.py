"""Tests for the execution-free promotion eligibility contract."""

import unittest

from core.evaluation.evidence import EvidenceSnapshot
from core.evaluation.promotion import PromotionGate


class PromotionGateTests(unittest.TestCase):
    def snapshot(self, commit="commit-1", evidence=None):
        return EvidenceSnapshot.create(
            "HES Trade Agent",
            "Seyed Hesameddin Beheshti Shirazi",
            commit,
            evidence or {"oos": True, "robustness": True},
        )

    def test_all_required_gates_pass(self):
        result = PromotionGate().evaluate(
            self.snapshot(), "commit-1", ("oos", "robustness")
        )
        self.assertTrue(result.eligible)
        self.assertEqual(result.reasons, ())

    def test_stale_evidence_blocks_eligibility(self):
        result = PromotionGate().evaluate(self.snapshot(), "commit-2", ("oos",))
        self.assertFalse(result.eligible)
        self.assertIn("stale_source_commit", result.reasons)

    def test_failed_required_evidence_blocks_eligibility(self):
        result = PromotionGate().evaluate(
            self.snapshot(evidence={"oos": True, "robustness": False}),
            "commit-1",
            ("oos", "robustness"),
        )
        self.assertFalse(result.eligible)
        self.assertIn("failed_evidence:robustness", result.reasons)

    def test_missing_required_evidence_blocks_eligibility(self):
        result = PromotionGate().evaluate(
            self.snapshot(evidence={"oos": True}),
            "commit-1",
            ("oos", "robustness"),
        )
        self.assertFalse(result.eligible)
        self.assertIn("missing_evidence:robustness", result.reasons)

    def test_invalid_snapshot_blocks_eligibility(self):
        snapshot = EvidenceSnapshot(
            "HES Trade Agent",
            "Seyed Hesameddin Beheshti Shirazi",
            "commit-1",
            (("oos", True),),
            "0" * 64,
        )
        result = PromotionGate().evaluate(snapshot, "commit-1", ("oos",))
        self.assertFalse(result.eligible)
        self.assertIn("snapshot_digest_invalid", result.reasons)

    def test_empty_required_gates_are_fail_closed(self):
        result = PromotionGate().evaluate(self.snapshot(), "commit-1", ())
        self.assertFalse(result.eligible)
        self.assertIn("no_required_gates", result.reasons)

    def test_invalid_gate_name_blocks_eligibility(self):
        result = PromotionGate().evaluate(
            self.snapshot(), "commit-1", ("oos", " ")
        )
        self.assertFalse(result.eligible)
        self.assertIn("invalid_required_gate_name", result.reasons)

    def test_duplicate_gate_names_are_deterministically_collapsed(self):
        result = PromotionGate().evaluate(
            self.snapshot(), "commit-1", ("oos", "oos", "robustness")
        )
        self.assertTrue(result.eligible)
        self.assertEqual(result.reasons, ())

    def test_empty_current_source_commit_blocks_eligibility(self):
        result = PromotionGate().evaluate(self.snapshot(), "", ("oos",))
        self.assertFalse(result.eligible)
        self.assertIn("invalid_current_source_commit", result.reasons)

    def test_non_string_gate_name_blocks_eligibility(self):
        result = PromotionGate().evaluate(self.snapshot(), "commit-1", ("oos", 1))
        self.assertFalse(result.eligible)
        self.assertIn("invalid_required_gate_name", result.reasons)


if __name__ == "__main__":
    unittest.main()
