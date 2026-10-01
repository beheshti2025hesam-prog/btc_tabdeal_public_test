"""Integrity tests for the mechanical real-data OOS snapshot."""
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class OOSSnapshotIntegrityTests(unittest.TestCase):
    def test_snapshot_reconciles_and_hashes_are_deterministic(self):
        repo_root = Path(__file__).resolve().parents[2]
        script = repo_root / "scripts" / "build_oos_snapshot.py"
        raw = repo_root / "data" / "trades.csv"

        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "snapshot.json"
            completed = subprocess.run(
                [sys.executable, str(script), "--csv", str(raw), "--output", str(output)],
                cwd=repo_root,
                check=True,
                capture_output=True,
                text=True,
            )
            self.assertIn('"evaluated": 1049', completed.stdout)

            snapshot = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(snapshot["reconciliation"]["fold_count"], 8)
            self.assertEqual(snapshot["reconciliation"]["population_count"], 1049)
            self.assertTrue(snapshot["reconciliation"]["matches_1049"])
            self.assertEqual(
                snapshot["population"]["gross_distribution_bps"],
                {
                    "negative_below_0bps": 479,
                    "zero_to_14bps_inclusive": 556,
                    "above_14bps": 14,
                },
            )
            self.assertEqual(len(snapshot["population"]["rows"]), 1049)

            population = snapshot["population"]
            canonical_population = (
                json.dumps(
                    population,
                    sort_keys=True,
                    separators=(",", ":"),
                    ensure_ascii=True,
                )
                + "\n"
            ).encode("utf-8")
            self.assertEqual(
                snapshot["snapshot"]["population_sha256"],
                hashlib.sha256(canonical_population).hexdigest(),
            )

            manifest = dict(snapshot)
            manifest["snapshot"] = dict(snapshot["snapshot"])
            expected_manifest_hash = manifest["snapshot"].pop("manifest_sha256", None)
            manifest_bytes = (
                json.dumps(
                    manifest,
                    sort_keys=True,
                    separators=(",", ":"),
                    ensure_ascii=True,
                )
                + "\n"
            ).encode("utf-8")
            self.assertEqual(
                expected_manifest_hash,
                hashlib.sha256(manifest_bytes).hexdigest(),
            )


if __name__ == "__main__":
    unittest.main()
