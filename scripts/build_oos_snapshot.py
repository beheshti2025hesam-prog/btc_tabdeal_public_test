"""Build a deterministic, execution-free OOS evidence snapshot.

The snapshot is a lineage manifest plus the exact evaluated OOS population
derived from one raw CSV input. It never mutates trading state or executes
orders. The population hash is computed from canonical JSON before the final
manifest hash is added.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

from core.backtest.oos_protocol import REAL_BTC_USDT_OOS_V1
from core.backtest.real_data import RealDataBacktest
from core.backtest.engine import BacktestSample


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sample_row(fold_index: int, sample: BacktestSample) -> dict:
    decision = sample.decision.value
    risk = sample.risk.value
    if decision == "NO_TRADE" or risk == "VETO":
        evaluated = False
        gross_return = None
    else:
        direction = 1.0 if decision == "LONG" else -1.0
        gross_return = direction * (sample.exit_price - sample.entry_price) / sample.entry_price
        evaluated = True
    return {
        "fold_index": fold_index,
        "timestamp": sample.timestamp.isoformat(),
        "decision": decision,
        "risk": risk,
        "entry_price": sample.entry_price,
        "exit_price": sample.exit_price,
        "evaluated": evaluated,
        "gross_return": gross_return,
        "gross_return_bps": gross_return * 10_000.0 if gross_return is not None else None,
    }


def canonical_bytes(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n").encode("utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", default="data/trades.csv")
    parser.add_argument("--output", default="oos_snapshot_integrity_v1.json")
    args = parser.parse_args()

    csv_path = Path(args.csv)
    if not csv_path.is_file():
        raise FileNotFoundError(f"raw input not found: {csv_path}")

    runner = RealDataBacktest(str(csv_path))
    wf = runner.run_walk_forward(
        train_size=REAL_BTC_USDT_OOS_V1.train_size,
        test_size=REAL_BTC_USDT_OOS_V1.test_size,
        step_size=REAL_BTC_USDT_OOS_V1.step_size,
        embargo_size=REAL_BTC_USDT_OOS_V1.embargo_size,
        max_folds=REAL_BTC_USDT_OOS_V1.expected_fold_count,
    )

    population = [
        sample_row(fold.index, sample)
        for fold in wf.folds
        for sample in fold.test_samples
        if sample.decision.value != "NO_TRADE" and sample.risk.value != "VETO"
    ]

    if len(wf.folds) != 8:
        raise AssertionError(f"expected 8 folds, got {len(wf.folds)}")
    if len(population) != 1049:
        raise AssertionError(f"expected 1049 evaluated samples, got {len(population)}")

    bands = {
        "negative_below_0bps": sum(row["gross_return_bps"] < 0 for row in population),
        "zero_to_14bps_inclusive": sum(0 <= row["gross_return_bps"] <= 14 for row in population),
        "above_14bps": sum(row["gross_return_bps"] > 14 for row in population),
    }
    if bands != {
        "negative_below_0bps": 479,
        "zero_to_14bps_inclusive": 556,
        "above_14bps": 14,
    }:
        raise AssertionError(f"gross distribution mismatch: {bands}")
    if sum(bands.values()) != 1049:
        raise AssertionError("gross distribution does not reconcile to 1049")

    snapshot = {
        "snapshot": {
            "schema": "hes.oos.snapshot.v1",
            "snapshot_id": "real-btcusdt-oos-v1",
            "repository_commit": os.environ.get("GITHUB_SHA", "unknown"),
            "raw_input": str(csv_path),
            "raw_input_sha256": sha256_file(csv_path),
        },
        "protocol": {
            "protocol_id": REAL_BTC_USDT_OOS_V1.protocol_id,
            "train_size": REAL_BTC_USDT_OOS_V1.train_size,
            "test_size": REAL_BTC_USDT_OOS_V1.test_size,
            "step_size": REAL_BTC_USDT_OOS_V1.step_size,
            "embargo_size": REAL_BTC_USDT_OOS_V1.embargo_size,
            "expected_fold_count": REAL_BTC_USDT_OOS_V1.expected_fold_count,
        },
        "population": {
            "rows": population,
            "count": len(population),
            "gross_distribution_bps": bands,
        },
        "reconciliation": {
            "fold_count": len(wf.folds),
            "walk_forward_evaluated": wf.evaluated,
            "population_count": len(population),
            "matches_1049": wf.evaluated == 1049 == len(population),
            "distribution_sum": sum(bands.values()),
            "matches_distribution": sum(bands.values()) == 1049,
        },
        "safety": {
            "execution": False,
            "parameter_tuning": False,
            "model_fitting": False,
            "capital_mutation": False,
        },
    }

    population_hash = hashlib.sha256(canonical_bytes(snapshot["population"])).hexdigest()
    snapshot["snapshot"]["population_sha256"] = population_hash
    snapshot["snapshot"]["manifest_sha256"] = hashlib.sha256(canonical_bytes(snapshot)).hexdigest()

    output = Path(args.output)
    output.write_bytes(canonical_bytes(snapshot))
    print(json.dumps({
        "output": str(output),
        "raw_input_sha256": snapshot["snapshot"]["raw_input_sha256"],
        "population_sha256": population_hash,
        "manifest_sha256": snapshot["snapshot"]["manifest_sha256"],
        "fold_count": len(wf.folds),
        "evaluated": len(population),
        "distribution": bands,
    }, indent=2))


if __name__ == "__main__":
    main()
