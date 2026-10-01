#!/usr/bin/env python3
"""Execution-free candidate performance study.

Consumes the descriptive OOS audit generated from the immutable fresh snapshot.
No threshold search, fitting, ranking-based selection, promotion, or execution.
"""
from __future__ import annotations
import json, math, statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "14_vs_1035_contrast_audit.json"
OUT = ROOT / "candidate_performance_study_v1.json"
FEATURES = {
    "Buy Ratio": "buy_ratio",
    "Delta": "buy_sell_delta",
    "Trade Count": "trade_count",
}
EXPECTED = {
    "blob": "b296b1c95f075518bea0b56fd11bbf5f0f613a04",
    "commit": "86631f2522aa74a38cfa21fa28afe8d49fbc5f20",
}
THRESHOLD = 0.0014

def ranks(values):
    order = sorted(range(len(values)), key=lambda i: values[i])
    out = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        rank = (i + j + 2) / 2.0
        for k in range(i, j + 1):
            out[order[k]] = rank
        i = j + 1
    return out

def auc(winners, controls):
    if not winners or not controls:
        return None
    combined = winners + controls
    r = ranks(combined)
    n1, n0 = len(winners), len(controls)
    u = sum(r[:n1]) - n1 * (n1 + 1) / 2
    return u / (n1 * n0)

def smd(a, b):
    if len(a) < 2 or len(b) < 2:
        return None
    va, vb = statistics.pvariance(a), statistics.pvariance(b)
    pooled = math.sqrt((va + vb) / 2)
    return (statistics.fmean(a) - statistics.fmean(b)) / pooled if pooled else 0.0

def main():
    d = json.loads(SOURCE.read_text(encoding="utf-8"))
    p = d["protocol"]
    assert p["snapshot_data_blob_sha"] == EXPECTED["blob"]
    assert p["snapshot_source_commit"] == EXPECTED["commit"]
    assert p["gross_threshold"] == THRESHOLD
    winners = d["winners"]
    assert len(winners) == 14
    assert d["counts"] == {"winners_gt_14bps": 14, "controls_le_14bps": 1035}

    controls = []
    # Reconstruct controls from the immutable audit's feature-level counts is not
    # sufficient for rank association, so this study intentionally uses the
    # winner/control feature populations emitted by the audit's contrast section
    # only for fixed, descriptive SMDs and uses winner-only temporal diagnostics.
    feature_results = {}
    for name, key in FEATURES.items():
        c = d["feature_contrast"][key]["controls"]
        w = d["feature_contrast"][key]["winners"]
        feature_results[name] = {
            "winner_n": w["n"],
            "control_n": c["n"],
            "winner_mean": w["mean"],
            "control_mean": c["mean"],
            "winner_median": w["median"],
            "control_median": c["median"],
            "smd": d["feature_contrast"][key]["smd"],
            "winner_range": d["feature_contrast"][key]["winner_range"],
            "interpretation": "descriptive separation only; no predictive threshold inferred",
        }

    fold = d["categorical"]["fold_winners"]
    supported = [int(k) for k, v in fold.items() if v > 0]
    fold_share = max(fold.values()) / len(winners)
    result = {
        "status": "CANDIDATE_PERFORMANCE_STUDY_REVIEW_ONLY",
        "candidate_id": "CANDIDATE_RESEARCH_V1",
        "lineage": {
            "snapshot_data_blob_sha": EXPECTED["blob"],
            "snapshot_source_commit": EXPECTED["commit"],
        },
        "population": {
            "evaluated_oos": 1049,
            "winners_gt_14bps": 14,
            "controls_le_14bps": 1035,
            "fixed_cost_boundary": "14bps gross threshold inherited from prior evidence; not tuned",
        },
        "candidate_features": feature_results,
        "temporal_evidence": {
            "supported_folds": supported,
            "supported_fold_count": len(supported),
            "total_folds": 8,
            "largest_winner_fold_share": fold_share,
            "kish_ess_approx": 2.9696969696969697,
            "winner_counts_by_fold": fold,
        },
        "interpretation": {
            "status": "DESCRIPTIVE_ONLY",
            "claim": "Candidate features show the previously observed descriptive separation on the fixed winner/control population, but the small and temporally clustered winner population limits independent evidence.",
            "predictive_performance_established": False,
            "signal_quality_established": False,
            "threshold_optimized": False,
        },
        "claim_boundary": {
            "threshold_tuned": False,
            "model_fitted": False,
            "signal_created": False,
            "promotion_decision": False,
            "live_execution": False,
        },
        "next_gate": "Human review of this artifact before any Signal research.",
    }
    OUT.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({
        "status": result["status"],
        "evaluated_oos": 1049,
        "winners": 14,
        "controls": 1035,
        "supported_folds": supported,
        "largest_winner_fold_share": fold_share,
    }, indent=2))

if __name__ == "__main__":
    main()
