#!/usr/bin/env python3
"""Sample-level outcome-timestamp / embargo boundary audit."""
from __future__ import annotations
import json
from datetime import timedelta
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.backtest.real_data import RealDataBacktest

ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "14_vs_1035_contrast_audit.json"
OUTPUT = ROOT / "outcome_timestamp_embargo_boundary_audit.json"
EXPECTED_BLOB = "1a44d52a0588deb765bbbea04bfb5783dcb1050b"
EXPECTED_SOURCE_COMMIT = "b8c4fe4fa054dbfa4fca17d2f307d269c16335e1"
EXPECTED_RUN_ID = 36489452534
TRAIN, TEST, STEP, FOLDS = 800, 400, 400, 8
OUTCOME_DELTA_SECONDS = 60

def main() -> None:
    frozen = json.loads(INPUT.read_text(encoding="utf-8"))
    p = frozen["protocol"]
    assert p["snapshot_data_blob_sha"] == EXPECTED_BLOB
    assert p["snapshot_source_commit"] == EXPECTED_SOURCE_COMMIT
    assert p["snapshot_run_id"] == EXPECTED_RUN_ID
    assert (p["train"], p["test"], p["step"], p["folds"]) == (TRAIN, TEST, STEP, FOLDS)
    assert frozen["counts"]["winners_gt_14bps"] == 14
    assert frozen["counts"]["controls_le_14bps"] == 1035

    wf = RealDataBacktest(csv_path="data/trades.csv").run_walk_forward(
        train_size=TRAIN, test_size=TEST, step_size=STEP, embargo_size=0, max_folds=FOLDS
    )
    assert len(wf.folds) == FOLDS
    assert wf.evaluated == 1049

    winner_timestamps = {r["timestamp"] for r in frozen["winners"]}
    fold_rows, sample_rows = [], []

    for fold in wf.folds:
        train_outcome = fold.train_end + timedelta(seconds=OUTCOME_DELTA_SECONDS)
        e1_test_start = fold.test_start + timedelta(seconds=OUTCOME_DELTA_SECONDS)
        fold_rows.append({
            "fold_index": fold.index,
            "train_end": fold.train_end.isoformat(),
            "train_outcome_timestamp": train_outcome.isoformat(),
            "historical_test_start_e0": fold.test_start.isoformat(),
            "test_first_outcome_timestamp": (fold.test_start + timedelta(seconds=OUTCOME_DELTA_SECONDS)).isoformat(),
            "historical_embargo_observations": 0,
            "train_outcome_equals_test_start_e0": train_outcome == fold.test_start,
            "e0_boundary_status": "CROSS_BOUNDARY_OUTCOME" if train_outcome >= fold.test_start else "SAFE",
            "hypothetical_e1_test_start": e1_test_start.isoformat(),
            "hypothetical_e1_safe": train_outcome < e1_test_start,
            "minimum_embargo_observations_for_60s_outcome": 1,
        })
        for sample_index, sample in enumerate(fold.test_samples):
            outcome_ts = sample.timestamp + timedelta(seconds=OUTCOME_DELTA_SECONDS)
            direction = sample.decision.value
            gross = None
            if sample.entry_price:
                if direction == "LONG":
                    gross = (sample.exit_price - sample.entry_price) / sample.entry_price
                elif direction == "SHORT":
                    gross = (sample.entry_price - sample.exit_price) / sample.entry_price
            sample_rows.append({
                "global_oos_index": fold.index * TEST + sample_index,
                "fold_index": fold.index,
                "sample_timestamp": sample.timestamp.isoformat(),
                "outcome_timestamp": outcome_ts.isoformat(),
                "outcome_offset_seconds": OUTCOME_DELTA_SECONDS,
                "direction": direction,
                "gross_return_recomputed_for_audit": gross,
                "is_frozen_winner": sample.timestamp.isoformat() in winner_timestamps,
                "outcome_is_after_test_start": outcome_ts >= fold.test_start,
                "outcome_is_after_test_end": outcome_ts > fold.test_end,
            })

    assert len(sample_rows) == 1049
    assert sum(r["is_frozen_winner"] for r in sample_rows) == 14
    assert all(r["outcome_offset_seconds"] == 60 for r in sample_rows)
    assert all(r["e0_boundary_status"] == "CROSS_BOUNDARY_OUTCOME" for r in fold_rows)
    assert all(r["hypothetical_e1_safe"] for r in fold_rows)

    result = {
        "status": "evidence-only",
        "lineage": {"snapshot_data_blob_sha": EXPECTED_BLOB, "snapshot_source_commit": EXPECTED_SOURCE_COMMIT, "snapshot_source_run_id": EXPECTED_RUN_ID},
        "protocol": {"train": TRAIN, "test": TEST, "step": STEP, "folds": FOLDS, "historical_embargo_observations": 0, "outcome_definition": "next contiguous 1-minute candle close", "outcome_timestamp_rule": "sample_timestamp + 60 seconds"},
        "population": {"evaluated_oos_samples": len(sample_rows), "frozen_winners": sum(r["is_frozen_winner"] for r in sample_rows), "controls": len(sample_rows) - sum(r["is_frozen_winner"] for r in sample_rows)},
        "fold_boundary_audit": fold_rows,
        "sample_level_audit": sample_rows,
        "boundary_conclusion": {"historical_e0_status": "CROSS_BOUNDARY_OUTCOME", "affected_fold_boundaries": len(fold_rows), "minimum_embargo_observations": 1, "minimum_embargo_seconds": 60, "historical_protocol_modified": False, "interpretation": "For future learned-model use, e0 is not sufficient: the last training observation's realized outcome timestamp equals the first OOS test timestamp at every fold boundary."},
        "claim_boundary": {"signal_created": False, "threshold_tuned": False, "model_fitting": False, "live_execution": False, "promotion_decision": False, "control_reconstruction": False},
    }
    OUTPUT.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({"status": result["status"], "evaluated_oos_samples": len(sample_rows), "frozen_winners": sum(r["is_frozen_winner"] for r in sample_rows), "fold_boundaries_crossed_at_e0": len(fold_rows), "minimum_embargo_observations": 1}, indent=2))

if __name__ == "__main__":
    main()
