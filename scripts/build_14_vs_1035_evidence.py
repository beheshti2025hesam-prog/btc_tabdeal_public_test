#!/usr/bin/env python3
"""Deterministic evidence synthesis for the frozen 14-vs-1035 OOS audit.

This script only reconciles already-generated, execution-free evidence.
It does not tune parameters, fit models, select a threshold, or build a Signal.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRAST = ROOT / "14_vs_1035_contrast_audit.json"
OOS = ROOT / "oos_cost_matrix_evidence.json"
TRADES = ROOT / "data" / "trades.csv"

EXPECTED_BLOB = "1a44d52a0588deb765bbbea04bfb5783dcb1050b"
EXPECTED_SOURCE_COMMIT = "b8c4fe4fa054dbfa4fca17d2f307d269c16335e1"
EXPECTED_RUN_ID = 36489452534
EXPECTED_THRESHOLD = 0.0014


def git_blob_sha(path: Path) -> str:
    data = path.read_bytes()
    header = f"blob {len(data)}\0".encode()
    return hashlib.sha1(header + data).hexdigest()


def main() -> None:
    contrast = json.loads(CONTRAST.read_text(encoding="utf-8"))
    oos = json.loads(OOS.read_text(encoding="utf-8"))

    protocol = contrast["protocol"]
    assert protocol["train"] == 800
    assert protocol["test"] == 400
    assert protocol["step"] == 400
    assert protocol["folds"] == 8
    assert protocol["gross_threshold"] == EXPECTED_THRESHOLD
    assert protocol["snapshot_data_blob_sha"] == EXPECTED_BLOB
    assert protocol["snapshot_source_commit"] == EXPECTED_SOURCE_COMMIT
    assert protocol["snapshot_run_id"] == EXPECTED_RUN_ID

    actual_blob = git_blob_sha(TRADES)
    assert actual_blob == EXPECTED_BLOB, (actual_blob, EXPECTED_BLOB)

    assert oos["protocol"] == {
        "protocol_id": "oos-real-btcusdt-v1-800x400x400-e0",
        "train_size": 800,
        "test_size": 400,
        "step_size": 400,
        "embargo_size": 0,
        "expected_fold_count": 8,
    }

    evaluated = oos["walk_forward"]["evaluated"]
    wins = oos["walk_forward"]["wins"]
    losses = oos["walk_forward"]["losses"]
    winners = contrast["winners"]
    winner_count = contrast["counts"]["winners_gt_14bps"]
    control_count = contrast["counts"]["controls_le_14bps"]

    assert evaluated == 1049
    assert wins == 528
    assert losses == 479
    assert winner_count == 14
    assert control_count == 1035
    assert winner_count + control_count == evaluated
    assert wins + losses == evaluated

    # Gross-return population buckets:
    #   < 0      -> losses
    #   0..14bps -> all remaining positive/zero observations below the winner boundary
    #   > 14bps  -> the 14 audited winners
    below_zero = losses
    above_14bps = winner_count
    zero_to_14bps = evaluated - below_zero - above_14bps
    assert (below_zero, zero_to_14bps, above_14bps) == (479, 556, 14)

    # The 14bps boundary is exactly 5bps fee + 2bps slippage per side.
    cost_rows = [
        row for row in oos["cost_matrix"]["aggregate"]
        if row["transaction_cost_bps_per_side"] == 5.0
        and row["slippage_bps_per_side"] == 2.0
    ]
    assert len(cost_rows) == 1
    cost = cost_rows[0]
    assert cost["evaluated"] == evaluated
    assert cost["wins"] == 14
    assert cost["losses"] == 1035

    fold_evidence = []
    for fold in range(8):
        rows = [r for r in winners if r["fold_index"] == fold]
        gross_sum = sum(r["gross_return"] for r in rows)
        net_sum = gross_sum - len(rows) * EXPECTED_THRESHOLD
        fold_evidence.append({
            "fold_index": fold,
            "winner_count": len(rows),
            "winner_gross_sum": gross_sum,
            "winner_net_sum_after_14bps_round_trip": net_sum,
            "winner_timestamps": [r["timestamp"] for r in rows],
        })

    assert sum(row["winner_count"] for row in fold_evidence) == 14

    result = {
        "status": "evidence-only",
        "protocol": {
            "train": 800,
            "test": 400,
            "step": 400,
            "embargo": 0,
            "folds": 8,
            "gross_winner_boundary": EXPECTED_THRESHOLD,
            "cost_equivalent": {
                "transaction_cost_bps_per_side": 5.0,
                "slippage_bps_per_side": 2.0,
                "round_trip_bps": 14.0,
            },
        },
        "lineage": {
            "snapshot_data_blob_sha": EXPECTED_BLOB,
            "snapshot_source_commit": EXPECTED_SOURCE_COMMIT,
            "snapshot_source_run_id": EXPECTED_RUN_ID,
            "current_data_blob_sha_verified": actual_blob,
        },
        "population": {
            "evaluated_oos": evaluated,
            "negative_gross_count": below_zero,
            "zero_to_14bps_count": zero_to_14bps,
            "greater_than_14bps_count": above_14bps,
            "reconciles": below_zero + zero_to_14bps + above_14bps == evaluated,
        },
        "cost_boundary": {
            "evaluated": cost["evaluated"],
            "net_positive_after_14bps_count": cost["wins"],
            "net_non_positive_after_14bps_count": cost["losses"],
            "aggregate_net_return": cost["total_net_return"],
        },
        "fold_survival": fold_evidence,
        "sample_trace": {
            "count": len(winners),
            "fields": [
                "timestamp", "sequence_first", "sequence_last", "direction",
                "entry_price", "exit_price", "gross_return",
                "ema_distance_pct", "vwap_distance_pct", "buy_ratio",
                "buy_sell_delta", "trade_count", "fold_index", "fold_regime"
            ],
            "samples": winners,
        },
        "interpretation_boundary": {
            "signal_created": False,
            "threshold_tuned": False,
            "parameter_tuning": False,
            "model_fitting": False,
            "live_execution": False,
            "promotion_decision": False,
        },
    }

    (ROOT / "14_vs_1035_evidence.json").write_text(
        json.dumps(result, indent=2), encoding="utf-8"
    )
    print(json.dumps({
        "population": result["population"],
        "cost_boundary": result["cost_boundary"],
        "fold_winner_counts": [x["winner_count"] for x in fold_evidence],
        "lineage_verified": actual_blob == EXPECTED_BLOB,
    }, indent=2))


if __name__ == "__main__":
    main()
