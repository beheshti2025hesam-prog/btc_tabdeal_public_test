"""Verify a frozen OOS snapshot and replay costs from its stored population.

This verifier never rebuilds the candidate population for cost evaluation:
it validates hashes, independently rebuilds only to verify lineage equality,
then reapplies explicit cost assumptions to the frozen rows.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys
import tempfile

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.backtest.costs import BacktestCostModel, CostScenario

SCENARIOS = ((0.0, 0.0), (5.0, 2.0), (10.0, 5.0))


def canonical_bytes(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n").encode("utf-8")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_snapshot(snapshot: dict, raw_path: Path) -> dict:
    meta = snapshot["snapshot"]
    population = snapshot["population"]
    rows = population["rows"]

    if sha256_file(raw_path) != meta["raw_input_sha256"]:
        raise AssertionError("raw input SHA-256 mismatch")
    if hashlib.sha256(canonical_bytes(population)).hexdigest() != meta["population_sha256"]:
        raise AssertionError("population SHA-256 mismatch")

    manifest = json.loads(json.dumps(snapshot))
    expected_manifest = manifest["snapshot"].pop("manifest_sha256")
    if hashlib.sha256(canonical_bytes(manifest)).hexdigest() != expected_manifest:
        raise AssertionError("manifest SHA-256 mismatch")

    if snapshot["protocol"]["expected_fold_count"] != 8:
        raise AssertionError("protocol fold count is not 8")
    if len(rows) != 1049 or population["count"] != 1049:
        raise AssertionError("frozen population count is not 1049")

    bands = {"negative_below_0bps": 0, "zero_to_14bps_inclusive": 0, "above_14bps": 0}
    for row in rows:
        if not row["evaluated"] or row["decision"] not in ("LONG", "SHORT"):
            raise AssertionError("snapshot contains a non-evaluable row")
        entry, exit_price = float(row["entry_price"]), float(row["exit_price"])
        if not (math.isfinite(entry) and math.isfinite(exit_price) and entry > 0 and exit_price > 0):
            raise AssertionError("invalid price in frozen row")
        direction = 1.0 if row["decision"] == "LONG" else -1.0
        gross = direction * (exit_price - entry) / entry
        if not math.isclose(gross, row["gross_return"], rel_tol=1e-12, abs_tol=1e-15):
            raise AssertionError("stored gross return does not match frozen prices")
        bps = gross * 10000.0
        if not math.isclose(bps, row["gross_return_bps"], rel_tol=1e-12, abs_tol=1e-12):
            raise AssertionError("stored gross bps mismatch")
        if bps < 0:
            bands["negative_below_0bps"] += 1
        elif bps <= 14:
            bands["zero_to_14bps_inclusive"] += 1
        else:
            bands["above_14bps"] += 1
    if bands != {"negative_below_0bps": 479, "zero_to_14bps_inclusive": 556, "above_14bps": 14}:
        raise AssertionError(f"gross bands mismatch: {bands}")

    # Independent deterministic rebuild verifies that the frozen rows still
    # correspond to the raw input/protocol; costs below use snapshot rows only.
    with tempfile.TemporaryDirectory() as tmp:
        rebuilt_path = Path(tmp) / "rebuilt.json"
        subprocess.run(
            [sys.executable, str(REPO_ROOT / "scripts" / "build_oos_snapshot.py"),
             "--csv", str(raw_path), "--output", str(rebuilt_path)],
            cwd=REPO_ROOT, check=True, capture_output=True, text=True,
        )
        rebuilt = json.loads(rebuilt_path.read_text(encoding="utf-8"))
    if rebuilt["population"]["rows"] != rows:
        raise AssertionError("independent raw replay differs from frozen population")
    if rebuilt["snapshot"]["raw_input_sha256"] != meta["raw_input_sha256"]:
        raise AssertionError("replayed raw input lineage differs")

    scenario_results = []
    for transaction_bps, slippage_bps in SCENARIOS:
        model = BacktestCostModel(transaction_bps, slippage_bps)
        returns = []
        for row in rows:
            # Construct only the mathematical inputs needed by the shared cost
            # model's formula; keep this replay independent of signal generation.
            gross = float(row["gross_return"])
            net = gross - 2.0 * (transaction_bps + slippage_bps) / 10000.0
            if not math.isfinite(net):
                raise AssertionError("non-finite replay return")
            returns.append(net)
        scenario_results.append({
            "transaction_cost_bps_per_side": transaction_bps,
            "slippage_bps_per_side": slippage_bps,
            "evaluated": len(returns),
            "total_net_return": sum(returns),
            "wins": sum(value > 0 for value in returns),
            "losses": sum(value < 0 for value in returns),
        })
    return {
        "status": "PASS",
        "raw_input_sha256": meta["raw_input_sha256"],
        "population_sha256": meta["population_sha256"],
        "manifest_sha256": expected_manifest,
        "fold_count": 8,
        "evaluated": len(rows),
        "gross_distribution_bps": bands,
        "cost_replay": scenario_results,
        "safety": {"execution": False, "parameter_tuning": False, "model_fitting": False, "capital_mutation": False},
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot", default="oos_snapshot_integrity_v1.json")
    parser.add_argument("--csv", default="data/trades.csv")
    parser.add_argument("--output", default="oos_raw_replay_evidence_v1.json")
    args = parser.parse_args()
    snapshot = json.loads(Path(args.snapshot).read_text(encoding="utf-8"))
    evidence = verify_snapshot(snapshot, Path(args.csv))
    Path(args.output).write_bytes(canonical_bytes(evidence))
    print(json.dumps(evidence, indent=2))


if __name__ == "__main__":
    main()
