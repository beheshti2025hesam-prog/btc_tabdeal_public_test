#!/usr/bin/env python3
"""Leave-one-fold-out, fold/regime survival, and independence-adjusted feature evidence.

Evidence-only layer over the frozen 14-vs-1035 OOS contrast audit.
The temporal test fold remains the independence unit. No threshold fitting,
Signal construction, model fitting, live execution, or promotion decision.
"""
from __future__ import annotations

import json
import math
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "14_vs_1035_contrast_audit.json"
OUTPUT = ROOT / "loo_fold_regime_independence_evidence.json"

EXPECTED_BLOB = "1a44d52a0588deb765bbbea04bfb5783dcb1050b"
EXPECTED_SOURCE_COMMIT = "b8c4fe4fa054dbfa4fca17d2f307d269c16335e1"
EXPECTED_RUN_ID = 36489452534
EXPECTED_FOLDS = 8
EXPECTED_WINNERS = 14
EXPECTED_CONTROLS = 1035
FEATURES = [
    "ema_distance_pct",
    "vwap_distance_pct",
    "buy_ratio",
    "buy_sell_delta",
    "trade_count",
]


def mean(values):
    return statistics.fmean(values) if values else None


def smd(a, b):
    if not a or not b:
        return None
    va = statistics.pvariance(a) if len(a) > 1 else 0.0
    vb = statistics.pvariance(b) if len(b) > 1 else 0.0
    pooled = math.sqrt((va + vb) / 2.0)
    return (mean(a) - mean(b)) / pooled if pooled else 0.0


def kish_ess(cluster_sizes):
    total = sum(cluster_sizes)
    denom = sum(x * x for x in cluster_sizes)
    return total * total / denom if denom else 0.0


def feature_fold_evidence(winners, controls):
    rows = []
    supported = sorted(set(r["fold_index"] for r in winners))
    for fold in supported:
        wf = [r for r in winners if r["fold_index"] == fold]
        cf = [r for r in controls if r["fold_index"] == fold]
        row = {"fold_index": fold, "winner_n": len(wf), "control_n": len(cf)}
        for feature in FEATURES:
            row[feature] = smd([r[feature] for r in wf], [r[feature] for r in cf])
        rows.append(row)
    return rows


def sign_summary(values):
    clean = [v for v in values if v is not None and math.isfinite(v)]
    if not clean:
        return {"n": 0, "positive": 0, "negative": 0, "zero": 0, "sign_consistency": None}
    pos = sum(v > 0 for v in clean)
    neg = sum(v < 0 for v in clean)
    zero = len(clean) - pos - neg
    return {
        "n": len(clean),
        "positive": pos,
        "negative": neg,
        "zero": zero,
        "sign_consistency": max(pos, neg, zero) / len(clean),
        "mean_smd": statistics.fmean(clean),
        "median_smd": statistics.median(clean),
    }


def main():
    data = json.loads(INPUT.read_text(encoding="utf-8"))
    protocol = data["protocol"]

    assert protocol["snapshot_data_blob_sha"] == EXPECTED_BLOB
    assert protocol["snapshot_source_commit"] == EXPECTED_SOURCE_COMMIT
    assert protocol["snapshot_run_id"] == EXPECTED_RUN_ID
    assert protocol["folds"] == EXPECTED_FOLDS
    assert protocol["train"] == 800
    assert protocol["test"] == 400
    assert protocol["step"] == 400

    winners = data["winners"]
    controls = [
        r for r in data.get("all_evaluated_rows", [])
        if r.get("gross_return", 0.0) <= protocol["gross_threshold"]
    ]
    # The frozen audit intentionally stores winner rows, while control fold
    # counts are authoritative for population accounting. Feature-level
    # independence evidence therefore uses the existing fold-exclusion SMDs
    # plus winner-supported fold counts, without reconstructing controls.
    assert len(winners) == EXPECTED_WINNERS
    fold_winners = {int(k): int(v) for k, v in data["categorical"]["fold_winners"].items()}
    fold_controls = {int(k): int(v) for k, v in data["categorical"]["fold_controls"].items()}
    assert sum(fold_winners.values()) == EXPECTED_WINNERS
    assert sum(fold_controls.values()) == EXPECTED_CONTROLS

    supported = sorted(fold_winners)
    cluster_sizes = [fold_winners[f] for f in supported]
    winner_ess = kish_ess(cluster_sizes)

    fold_survival = []
    for fold in range(EXPECTED_FOLDS):
        remaining = EXPECTED_WINNERS - fold_winners.get(fold, 0)
        remaining_supported = sum(1 for f in supported if f != fold)
        loo = data["stability"]["fold_exclusion"].get(str(fold), {})
        fold_survival.append({
            "excluded_fold": fold,
            "winner_count_removed": fold_winners.get(fold, 0),
            "winner_count_remaining": remaining,
            "winner_supported_folds_remaining": remaining_supported,
            "remaining_winner_gross_sum": loo.get("winner_gross_sum_remaining"),
            "feature_smd_without_fold": loo.get("feature_smd_without_fold", {}),
        })

    fold_feature_rows = feature_fold_evidence(winners, controls)
    # Controls are not materialized in this snapshot, so calculate fold-level
    # feature evidence from the frozen leave-one-fold-out SMDs. This preserves
    # the already-computed contrast without fabricating control observations.
    feature_independence = {}
    for feature in FEATURES:
        loo_values = [
            data["stability"]["fold_exclusion"][str(f)]["feature_smd_without_fold"].get(feature)
            for f in range(EXPECTED_FOLDS)
            if feature in data["stability"]["fold_exclusion"][str(f)].get("feature_smd_without_fold", {})
        ]
        feature_independence[feature] = {
            "leave_one_fold_out_smd": {
                str(f): data["stability"]["fold_exclusion"][str(f)]["feature_smd_without_fold"].get(feature)
                for f in range(EXPECTED_FOLDS)
            },
            "loo_sign_summary": sign_summary(loo_values),
            "winner_supported_fold_smd": [
                row[feature] for row in fold_feature_rows if row[feature] is not None
            ],
            "control_reconstruction": False,
        }

    regime = data["categorical"]["regime_winners"]
    direction = data["categorical"]["direction_winners"]

    result = {
        "status": "evidence-only",
        "lineage": {
            "snapshot_data_blob_sha": EXPECTED_BLOB,
            "snapshot_source_commit": EXPECTED_SOURCE_COMMIT,
            "snapshot_source_run_id": EXPECTED_RUN_ID,
        },
        "frozen_population": {
            "nominal_winners": EXPECTED_WINNERS,
            "nominal_controls": EXPECTED_CONTROLS,
            "fold_count": EXPECTED_FOLDS,
            "winner_supported_fold_indices": supported,
            "winner_fold_sizes": cluster_sizes,
            "winner_kish_effective_sample_size": winner_ess,
        },
        "leave_one_fold_out": {
            "folds": fold_survival,
            "note": "Each exclusion is descriptive; no excluded-fold result is used to select a threshold or strategy.",
        },
        "fold_survival": {
            "supported_fold_count": len(supported),
            "support_fraction": len(supported) / EXPECTED_FOLDS,
            "winner_concentration": max(cluster_sizes) / EXPECTED_WINNERS,
            "winner_counts_by_fold": {str(k): fold_winners.get(k, 0) for k in range(EXPECTED_FOLDS)},
        },
        "regime_survival": {
            "winner_counts_by_regime": regime,
            "winner_counts_by_direction": direction,
            "note": "Regime and direction are descriptive partitions of the frozen audit; neither is used for selection.",
        },
        "independence_adjusted_feature_evidence": feature_independence,
        "claim_boundary": {
            "independence_unit": "walk_forward_test_fold",
            "nominal_winner_units": EXPECTED_WINNERS,
            "effective_winner_units": winner_ess,
            "signal_created": False,
            "threshold_tuned": False,
            "parameter_tuning": False,
            "model_fitting": False,
            "live_execution": False,
            "promotion_decision": False,
            "interpretation": "Descriptive stability only. The evidence does not treat 14 winners as 14 independent confirmations.",
        },
    }

    OUTPUT.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({
        "status": result["status"],
        "winner_ess": winner_ess,
        "supported_folds": supported,
        "support_fraction": len(supported) / EXPECTED_FOLDS,
    }, indent=2))


if __name__ == "__main__":
    main()
