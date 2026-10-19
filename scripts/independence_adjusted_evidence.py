#!/usr/bin/env python3
"""Independence-adjusted evidence for the frozen 14-vs-1035 OOS audit.

Unit of independence is the walk-forward test fold (a contiguous temporal block).
This is descriptive evidence only: no p-value hunting, threshold tuning, fitting,
or Signal construction.
"""
from __future__ import annotations

import json
import math
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "14_vs_1035_contrast_audit.json"
OUTPUT = ROOT / "independence_adjusted_evidence.json"

EXPECTED_BLOB = "1a44d52a0588deb765bbbea04bfb5783dcb1050b"
EXPECTED_SOURCE_COMMIT = "b8c4fe4fa054dbfa4fca17d2f307d269c16335e1"
EXPECTED_RUN_ID = 36489452534
FEATURES = ["ema_distance_pct", "vwap_distance_pct", "buy_ratio",
            "buy_sell_delta", "trade_count"]


def mean(xs):
    return statistics.fmean(xs) if xs else None


def kish_ess(cluster_sizes):
    total = sum(cluster_sizes)
    denom = sum(x * x for x in cluster_sizes)
    return (total * total / denom) if denom else 0.0


def smd(a, b):
    if not a or not b:
        return None
    va = statistics.pvariance(a) if len(a) > 1 else 0.0
    vb = statistics.pvariance(b) if len(b) > 1 else 0.0
    pooled = math.sqrt((va + vb) / 2.0)
    return (mean(a) - mean(b)) / pooled if pooled else 0.0


def feature_fold_table(winners, controls, feature):
    out = []
    folds = sorted(set(r["fold_index"] for r in winners))
    for fold in folds:
        w = [r[feature] for r in winners if r["fold_index"] == fold]
        c = [r[feature] for r in controls if r["fold_index"] == fold]
        out.append({
            "fold_index": fold,
            "winner_n": len(w),
            "control_n": len(c),
            "winner_mean": mean(w),
            "control_mean": mean(c),
            "paired_mean_difference": mean(w) - mean(c) if w and c else None,
            "within_fold_smd": smd(w, c),
        })
    return out


def loo_fold_ranges(rows):
    return {
        feature: {
            str(fold): smd(
                [r[feature] for r in rows["winners"] if r["fold_index"] != fold],
                [r[feature] for r in rows["controls"] if r["fold_index"] != fold],
            )
            for fold in sorted(set(r["fold_index"] for r in rows["winners"]))
        }
        for feature in FEATURES
    }


def main():
    data = json.loads(INPUT.read_text(encoding="utf-8"))
    protocol = data["protocol"]
    assert protocol["snapshot_data_blob_sha"] == EXPECTED_BLOB
    assert protocol["snapshot_source_commit"] == EXPECTED_SOURCE_COMMIT
    assert protocol["snapshot_run_id"] == EXPECTED_RUN_ID
    assert protocol["folds"] == 8
    assert protocol["train"] == 800
    assert protocol["test"] == 400
    assert protocol["step"] == 400

    winners = data["winners"]
    controls = []
    # Reconstruct control fold counts from the frozen audit summary. Individual
    # control rows are intentionally not required for this independence layer.
    fold_winner_counts = {int(k): v for k, v in data["categorical"]["fold_winners"].items()}
    fold_control_counts = {int(k): v for k, v in data["categorical"]["fold_controls"].items()}

    assert len(winners) == 14
    assert sum(fold_winner_counts.values()) == 14
    assert sum(fold_control_counts.values()) == 1035

    # Four distinct temporal test folds contain all 14 winners.
    winner_folds = sorted(fold_winner_counts)
    cluster_sizes = [fold_winner_counts[f] for f in winner_folds]
    winner_ess = kish_ess(cluster_sizes)

    # Fold-level support is the independence-adjusted unit: 4 temporal blocks,
    # not 14 nominal winner observations. The concentration ratio identifies
    # whether one fold dominates the winner population.
    max_fold_share = max(cluster_sizes) / sum(cluster_sizes)
    support_fraction = len(winner_folds) / protocol["folds"]

    # Existing stability output already contains leave-one-fold-out feature SMDs.
    existing_loo = data["stability"]["fold_exclusion"]
    loo = {}
    for fold_key, payload in existing_loo.items():
        loo[fold_key] = payload["feature_smd_without_fold"]

    result = {
        "status": "evidence-only",
        "independence_unit": {
            "unit": "walk_forward_test_fold",
            "reason": "Each fold is a contiguous temporal test block; individual trades within a block are not treated as independent observations.",
            "fold_count": protocol["folds"],
            "winner_supported_fold_count": len(winner_folds),
            "winner_supported_fold_indices": winner_folds,
        },
        "lineage": {
            "snapshot_data_blob_sha": EXPECTED_BLOB,
            "snapshot_source_commit": EXPECTED_SOURCE_COMMIT,
            "snapshot_source_run_id": EXPECTED_RUN_ID,
        },
        "population": {
            "nominal_winners": 14,
            "nominal_controls": 1035,
            "winner_fold_sizes": cluster_sizes,
            "winner_kish_effective_sample_size": winner_ess,
            "winner_fold_support_fraction": support_fraction,
            "largest_winner_fold_share": max_fold_share,
        },
        "fold_level_concentration": {
            "winner_counts_by_fold": {str(k): fold_winner_counts[k] for k in sorted(fold_winner_counts)},
            "control_counts_by_fold": {str(k): fold_control_counts[k] for k in sorted(fold_control_counts)},
            "winner_concentration_note": "7 of 14 winners occur in fold 3; folds 4-7 contain no winners.",
        },
        "leave_one_fold_out_feature_smd": loo,
        "interpretation": {
            "independence_adjusted_winner_units": len(winner_folds),
            "nominal_to_effective_ratio": winner_ess / 14.0,
            "signal_created": False,
            "threshold_tuned": False,
            "parameter_tuning": False,
            "model_fitting": False,
            "live_execution": False,
            "promotion_decision": False,
            "claim_boundary": "Descriptive stability only; four temporal folds are too few to treat the 14 winners as 14 independent confirmations.",
        },
    }

    OUTPUT.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({
        "winner_units": len(winner_folds),
        "winner_ess": winner_ess,
        "support_fraction": support_fraction,
        "largest_fold_share": max_fold_share,
        "status": result["status"],
    }, indent=2))


if __name__ == "__main__":
    main()
