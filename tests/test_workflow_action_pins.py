from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts.check_workflow_action_pins import find_unpinned_actions


class WorkflowActionPinPolicyTests(unittest.TestCase):
    def test_repository_workflows_use_immutable_external_action_refs(self):
        root = Path(__file__).resolve().parents[1]
        self.assertEqual(find_unpinned_actions(root / ".github" / "workflows"), [])

    def test_detects_mutable_tags_and_missing_refs_but_allows_local_actions(self):
        with tempfile.TemporaryDirectory() as directory:
            workflows = Path(directory)
            (workflows / "sample.yml").write_text(
                "jobs:\n  test:\n    steps:\n"
                "      - uses: actions/checkout@v7\n"
                "      - uses: vendor/action\n"
                "      - uses: ./.github/actions/local\n"
                "      - uses: actions/setup-python@" + "a" * 40 + "\n",
                encoding="utf-8",
            )
            failures = find_unpinned_actions(workflows)
        self.assertEqual(len(failures), 2)
        self.assertIn("full 40-character commit SHA", failures[0])
        self.assertIn("no immutable ref", failures[1])

    def test_rejects_short_or_non_hex_commit_identifiers(self):
        with tempfile.TemporaryDirectory() as directory:
            workflows = Path(directory)
            (workflows / "sample.yml").write_text(
                "steps:\n  - uses: actions/checkout@1234\n", encoding="utf-8"
            )
            failures = find_unpinned_actions(workflows)
        self.assertEqual(len(failures), 1)
        self.assertIn("full 40-character commit SHA", failures[0])


if __name__ == "__main__":
    unittest.main()
