"""Integrity tests for the mechanical real-data OOS snapshot."""
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from core.backtest.costs import CostScenario, evaluate_samples
from core.backtest.oos_protocol import REAL_BTC_USDT_OOS_V1
from core.backtest.real_data import RealDataBacktest


class OOSSnapshotIntegrityTests(unittest.TestCase):

    def test_snapshot_population_is_exactly_the_cost_matrix_population(self):
        repo_root = Path(__file__).resolve().parents[2]
        raw = repo_root / "data" / "trades.csv"

        runner = RealDataBacktest(str(raw))
        wf = runner.run_walk_forward(
            train_size=REAL_BTC_USDT_OOS_V1.train_size,
            test_size=REAL_BTC_USDT_OOS_V1.test_size,
            step_size=REAL_BTC_USDT_OOS_V1.step_size,
            embargo_size=REAL_BTC_USDT_OOS_V1.embargo_size,
            max_folds=REAL_BTC_USDT_OOS_V1.expected_fold_count,
        )

        expected = []
        for fold in wf.folds:
            for sample in fold.test_samples:
                if sample.decision.value == "NO_TRADE" or sample.risk.value == "VETO":
                    continue
                direction = 1.0 if sample.decision.value == "LONG" else -1.0
                gross = direction * (sample.exit_price - sample.entry_price) / sample.entry_price
                expected.append(
                    (
                        fold.index,
                        sample.timestamp.isoformat(),
                        sample.decision.value,
                        sample.risk.value,
                        sample.entry_price,
                        sample.exit_price,
                        gross,
                    )
                )

        matrix = evaluate_samples(
            tuple(sample for fold in wf.folds for sample in fold.test_samples),
            (CostScenario(0.0, 0.0),),
        )
        self.assertEqual(matrix[0][2], 1049)

        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "snapshot.json"
            subprocess.run(
                [
                    sys.executable,
                    str(repo_root / "scripts" / "build_oos_snapshot.py"),
                    "--csv",
                    str(raw),
                    "--output",
                    str(output),
                ],
                cwd=repo_root,
                check=True,
                capture_output=True,
                text=True,
            )
            snapshot = json.loads(output.read_text(encoding="utf-8"))

        actual = [
            (
                row["fold_index"],
                row["timestamp"],
                row["decision"],
                row["risk"],
                row["entry_price"],
                row["exit_price"],
                row["gross_return"],
            )
            for row in snapshot["population"]["rows"]
        ]
        self.assertEqual(actual, expected)

    def test_snapshot_reconciles_and_hashes_are_deterministic(self):
        repo_root = Path(__file__).resolve().parents[2]
        script = repo_root / "scripts" / "build_oos_snapshot.py"
        raw = repo_root / "data" / "trades.csv"

        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "snapshot.json"
            completed = subprocess.run(
                [sys.executable, str(script), "--csv", str(raw), "--output", str(output)],
                cwd=repo_root,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
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
