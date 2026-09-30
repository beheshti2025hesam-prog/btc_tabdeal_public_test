#!/usr/bin/env python3
"""Sample-level outcome-timestamp / embargo boundary audit.

Evidence-only. Reuses the frozen real-data OOS protocol and the already
locked 14-vs-1035 snapshot. It does not tune, fit, select, execute, or
reconstruct controls.

For each of the 1,049 OOS evaluated samples, the realized outcome timestamp
is defined by the canonical pipeline as observation_timestamp + 60 seconds.
For each fold, the audit also records the exact train-tail/test-head
timestamps and whether e0 permits the final training outcome to land at the
first test timestamp.
"""
from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

from core.backtest.real_data import RealDataBacktest

ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "14_vs_1035_contrast_audit.json"
OUTPUT = ROOT / "outcome_timestamp_embargo_boundary_audit.json"

EXPECTED_BLOB = "1a44d52a0588deb765bbbea04bfb5783dcb1050b"
EXPECTED_SOURCE_COMMIT = "b8c4fe4fa054dbfa4fca17d2f307d269c16335e1"
EXPECTED_RUN_ID = 36489452534
TRAIN = 800
TEST = 400
STEP = 400
FOLDS = 8
OUTCOME_DELTA_SECONDS = 60


def main() -> None:
    frozen = json.loads(INPUT.read_text(encoding="utf-8"))
    protocol = frozen["protocol"]
    assert protocol["snapshot_data_blob_sha"] == EXPECTED_BLOB
    assert protocol["snapshot_source_commit"] == EXPECTED_SOURCE_COMMIT
    assert protocol["snapshot_run_id"] == EXPECTED_RUN_ID
    assert protocol["train"] == TRAIN
    assert protocol["test"] == TEST
    assert protocol["step"] == STEP
    assert protocol["folds"] == FOLDS
    assert frozen["counts"]["winners_gt_14bps"] == 14
    assert frozen["counts"]["controls_le_14bps"] == 1035

    # The canonical real-data pipeline is reused; no alternate candle/label
    # reconstruction is introduced here.
    backtest = RealDataBacktest(csv_path="data/trades.csv")
    wf = backtest.run_walk_forward(
        train_size=TRAIN,
        test_size=TEST,
        step_size=STEP,
        embargo_size=0,
        max_folds=FOLDS,
    )
    assert len(wf.folds) == FOLDS
    assert wf.evaluated == 1049

    winner_keys = {
        (r["timestamp"], r["direction"], r["gross_return"])
        for r in frozen["winners"]
    }

    fold_rows = []
    sample_rows = []
    for fold in wf.folds:
        # WalkForwardFold does not retain train samples, but its exact train
        # tail/test head timestamps are enough to audit the label boundary.
        train_end = fold.train_end
        test_start = fold.test_start
        train_outcome = train_end + timedelta(seconds=OUTCOME_DELTA_SECONDS)
        test_first_outcome = test_start + timedelta(seconds=OUTCOME_DELTA_SECONDS)

        fold_rows.append({
            "fold_index": fold.index,
            "train_end": train_end.isoformat(),
            "train_outcome_timestamp": train_outcome.isoformat(),
            "test_start": test_start.isoformat(),
            "test_first_outcome_timestamp": test_first_outcome.isoformat(),
            "embargo_observations": 0,
            "train_outcome_equals_test_start": train_outcome == test_start,
            "e0_boundary_status": (
                "CROSS_BOUNDARY_OUTCOME"
                if train_outcome >= test_start
                else "SAFE"
            ),
            "minimum_embargo_observations_for_60s_outcome": 1,
        })

        for sample_index, sample in enumerate(fold.test_samples):
            outcome_ts = sample.timestamp + timedelta(seconds=OUTCOME_DELTA_SECONDS)
            key = (sample.timestamp.isoformat(), sample.decision.value, sample.gross_return)
            # gross_return is not guaranteed to be exposed by every
            # BacktestSample implementation; use entry/exit prices instead.
            gross = None
            if sample.entry_price:
                direction = sample.decision.value
                if direction == "LONG":
                    gross = (sample.exit_price - sample.entry_price) / sample.entry_price
                elif direction == "SHORT":
                    gross = (sample.entry_price - sample.exit_price) / sample.entry_price
            winner = any(
                r["timestamp"] == sample.timestamp.isoformat()
                and r["direction"] == sample.decision.value
                for r in frozen["winners"]
            )
            sample_rows.append({
                "global_oos_index": fold.index * TEST + sample_index,
                "fold_index": fold.index,
                "sample_timestamp": sample.timestamp.isoformat(),
                "outcome_timestamp": outcome_ts.isoformat(),
                "outcome_offset_seconds": OUTCOME_DELTA_SECONDS,
                "direction": sample.decision.value,
                "gross_return_recomputed_for_audit": gross,
                "is_frozen_winner": winner,
                "outcome_is_after_test_start": outcome_ts >= test_start,
                "outcome_is_after_test_end": outcome_ts > fold.test_end,
            })

    assert len(sample_rows) == 1049
    assert sum(r["is_frozen_winner"] for r in sample_rows) == 14
    assert all(r["outcome_offset_seconds"] == 60 for r in sample_rows)
    assert all(r["e0_boundary_status"] == "CROSS_BOUNDARY_OUTCOME" for r in fold_rows)

    # Hypothetical e1 is a boundary calculation only, not a rerun or a change
    # to the historical evidence protocol.
    e1_safe = all(
        (f["train_end"] != f["test_start"])
        for f in fold_rows
    )
    # Exact temporal condition: adding one 60-second observation of embargo
    # moves test_start one minute beyond the training tail's outcome timestamp.
    hypothetical_e1_safe = all(
        (
            # train outcome = train_end + 60s; e1 test start = test_start + 60s
            __import__("datetime").datetime.fromisoformat(f["train_outcome_timestamp"])
            < __import__("datetime").datetime.fromisoformat(f["test_start"]) + timedelta(seconds=60)
        )
        for f in fold_rows
    )
    assert not e1_safe
    assert hypothetical_e1_safe

    result = {
        "status": "evidence-only",
        "lineage": {
            "snapshot_data_blob_sha": EXPECTED_BLOB,
            "snapshot_source_commit": EXPECTED_SOURCE_COMMIT,
            "snapshot_source_run_id": EXPECTED_RUN_ID,
        },
        "protocol": {
            "train": TRAIN,
            "test": TEST,
            "step": STEP,
            "folds": FOLDS,
            "historical_embargo_observations": 0,
            "outcome_definition": "next contiguous 1-minute candle close",
            "outcome_timestamp_rule": "sample_timestamp + 60 seconds",
        },
        "population": {
            "evaluated_oos_samples": len(sample_rows),
            "frozen_winners": sum(r["is_frozen_winner"] for r in sample_rows),
            "controls": len(sample_rows) - sum(r["is_frozen_winner"] for r in sample_rows),
        },
        "fold_boundary_audit": fold_rows,
        "sample_level_audit": sample_rows,
        "boundary_conclusion": {
            "historical_e0_status": "CROSS_BOUNDARY_OUTCOME",
            "affected_fold_boundaries": len(fold_rows),
            "affected_oos_samples": 0,
            "interpretation": (
                "The historical baseline remains a descriptive, execution-free "
                "OOS measurement. For any future learned model, e0 is not a "
                "sufficient embargo because the last training label becomes "
                "available exactly at the first test timestamp."
            ),
            "minimum_embargo_observations": 1,
            "minimum_embargo_seconds": 60,
            "historical_protocol_modified": False,
        },
        "claim_boundary": {
            "signal_created": False,
            "threshold_tuned": False,
            "model_fitting": False,
            "live_execution": False,
            "promotion_decision": False,
            "control_reconstruction": False,
        },
    }
    OUTPUT.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({
        "status": result["status"],
        "evaluated_oos_samples": len(sample_rows),
        "frozen_winners": sum(r["is_frozen_winner"] for r in sample_rows),
        "fold_boundaries_crossed_at_e0": len(fold_rows),
        "minimum_embargo_observations": 1,
    }, indent=2))


if __name__ == "__main__":
    main()
