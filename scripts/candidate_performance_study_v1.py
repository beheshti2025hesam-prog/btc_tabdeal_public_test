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
    "blob": "b0e6667df6c9bfcbffffd04229702a9c6c694964",
    "commit": "583dfeb3e7cd09b2cdfdbabcd18604d3d6e608f6",
}
THRESHOLD = 0.0014

def smd(a, b):
    if len(a) < 2 or len(b) < 2:
        return None
    va, vb = statistics.pvariance(a), statistics.pvariance(b)
    pooled = math.sqrt((va + vb) / 2)
    return (statistics.fmean(a) - statistics.fmean(b)) / pooled if pooled else 0.0

def kish_ess(counts):
    total = sum(counts)
    denom = sum(n * n for n in counts)
    return (total * total / denom) if denom else 0.0

def main():
    d = json.loads(SOURCE.read_text(encoding="utf-8"))
    p = d["protocol"]
    assert p["snapshot_data_blob_sha"] == EXPECTED["blob"]
    assert p["snapshot_source_commit"] == EXPECTED["commit"]
    assert p["gross_threshold"] == THRESHOLD

    winners = d["winners"]
    counts = d["counts"]
    evaluated = d["population"]["evaluated_oos"]
    winner_n = counts["winners_gt_14bps"]
    control_n = counts["controls_le_14bps"]

    assert len(winners) == winner_n
    assert winner_n + control_n == evaluated
    assert winner_n > 0

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

    fold = {str(k): v for k, v in d["categorical"]["fold_winners"].items()}
    supported = sorted(int(k) for k, v in fold.items() if v > 0)
    fold_counts = [v for v in fold.values() if v > 0]
    fold_share = max(fold_counts) / winner_n if fold_counts else 0.0

    result = {
        "status": "CANDIDATE_PERFORMANCE_STUDY_REVIEW_ONLY",
        "candidate_id": "CANDIDATE_RESEARCH_V1",
        "lineage": {
            "snapshot_data_blob_sha": EXPECTED["blob"],
            "snapshot_source_commit": EXPECTED["commit"],
        },
        "population": {
            "evaluated_oos": evaluated,
            "winners_gt_14bps": winner_n,
            "controls_le_14bps": control_n,
            "fixed_cost_boundary": "14bps gross threshold inherited from prior evidence; not tuned",
        },
        "candidate_features": feature_results,
        "temporal_evidence": {
            "supported_folds": supported,
            "supported_fold_count": len(supported),
            "total_folds": 8,
            "largest_winner_fold_share": fold_share,
            "kish_ess_approx": kish_ess(fold_counts),
            "winner_counts_by_fold": fold,
        },
        "interpretation": {
            "status": "DESCRIPTIVE_ONLY",
            "claim": "Fresh-snapshot candidate performance is descriptive evidence only; winner concentration across temporal folds limits independent evidence.",
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
        "evaluated_oos": evaluated,
        "winners": winner_n,
        "controls": control_n,
        "supported_folds": supported,
        "largest_winner_fold_share": fold_share,
        "kish_ess_approx": result["temporal_evidence"]["kish_ess_approx"],
    }, indent=2))

if __name__ == "__main__":
    main()
