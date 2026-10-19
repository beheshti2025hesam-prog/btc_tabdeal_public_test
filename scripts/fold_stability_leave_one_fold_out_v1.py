#!/usr/bin/env python3
import json, math, statistics
from pathlib import Path

THRESHOLD = 0.0014
FOLDS = 8
FEATURES = ["ema_distance_pct", "vwap_distance_pct", "buy_ratio", "buy_sell_delta", "trade_count"]

def smd(a, b):
    va = statistics.pvariance(a) if len(a) > 1 else 0
    vb = statistics.pvariance(b) if len(b) > 1 else 0
    d = math.sqrt((va + vb) / 2)
    return (statistics.fmean(a) - statistics.fmean(b)) / d if d else 0.0

src = Path("protocol_reconciliation_full_population_audit.json")
if not src.exists():
    raise SystemExit("Missing frozen protocol output; run the immutable protocol first.")

d = json.loads(src.read_text(encoding="utf-8"))
winners = d["winners"]

# LOFO is a diagnostic exclusion calculation only: upstream population remains immutable.
lofo = {}
fold_counts = {str(i): sum(r["fold_index"] == i for r in winners) for i in range(FOLDS)}
total_gross = sum(r["gross_return"] for r in winners)

for fold in range(FOLDS):
    wf = [r for r in winners if r["fold_index"] != fold]
    removed = [r for r in winners if r["fold_index"] == fold]
    remaining_gross = sum(r["gross_return"] for r in wf)
    lofo[str(fold)] = {
        "winner_count_total": len(winners),
        "winner_count_removed": len(removed),
        "winner_count_remaining": len(wf),
        "removed_gross_sum": sum(r["gross_return"] for r in removed),
        "remaining_gross_sum": remaining_gross,
        "remaining_gross_mean": statistics.fmean(r["gross_return"] for r in wf) if wf else None,
        "remaining_direction_counts": {
            k: sum(r["direction"] == k for r in wf)
            for k in sorted(set(r["direction"] for r in winners))
        },
        "remaining_feature_smd_vs_all_winner_baseline": {
            f: (
                statistics.fmean([r[f] for r in wf])
                - statistics.fmean([r[f] for r in winners])
            ) / (statistics.pstdev([r[f] for r in winners]) or 1.0)
            for f in FEATURES
        },
    }

nonzero_folds = [int(k) for k, v in fold_counts.items() if v > 0]
top_fold = max(fold_counts, key=fold_counts.get)
top_share_pct = (fold_counts[top_fold] / len(winners) * 100.0) if winners else None

# The 14-Survivor aggregate is immutable reference data only. Aggregate fold counts
# are insufficient for exact Survivor LOFO because they do not identify the 14 rows.
survivor_fold_counts = {"0": 2, "1": 3, "2": 2, "3": 7, "4": 0, "5": 0, "6": 0, "7": 0}
survivor_reference = {
    "source": "evidence/downstream_cost_fold_survival_audit_v1.json",
    "source_commit": "e3f86f81c35506302e087fc8fc82bf972ac11a20",
    "round_trip_bps": 14,
    "fold_counts": survivor_fold_counts,
    "total": sum(survivor_fold_counts.values()),
    "lineage_records_not_reconstructed_here": True,
    "full_lofo_status": "BLOCKED_UNTIL_EXACT_14_SURVIVOR_LINEAGE_IS_AVAILABLE",
}

result = {
    "status": "PARTIAL_WINNER_LOFO_ONLY__FULL_28_PLUS_14_LOFO_BLOCKED",
    "scientific_boundary": {
        "winner_lofo_complete": True,
        "survivor_lofo_complete": False,
        "observation_removal": False,
        "threshold_tuning": False,
        "parameter_tuning": False,
        "selection": False,
        "promotion": False,
        "execution": False,
    },
    "protocol": {"train": 800, "test": 400, "step": 400, "folds": 8, "threshold_bps": 14},
    "winner_summary": {
        "total": len(winners),
        "fold_counts": fold_counts,
        "nonzero_fold_count": len(nonzero_folds),
        "top_fold": int(top_fold),
        "top_fold_share_pct": top_share_pct,
        "total_gross_sum": total_gross,
    },
    "winner_lofo": lofo,
    "survivor_14_reference": survivor_reference,
    "next_required_evidence": {
        "required": "Exact 14 Survivor lineage rows with observation identity and fold membership from the immutable 1,049 Evidence Lock.",
        "minimum_fields": ["observation_id", "fold", "timestamp", "sequence", "entry", "exit", "gross_outcome", "14bps_classification", "lineage"],
        "forbidden_substitute": "Aggregate fold counts alone must not be used as a surrogate for row-level Survivor LOFO.",
    },
}
Path("fold_stability_leave_one_fold_out_v1.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")

print(json.dumps({
    "status": result["status"],
    "winner_total": len(winners),
    "winner_fold_counts": fold_counts,
    "winner_top_fold_share_pct": top_share_pct,
    "survivor_14_fold_counts": survivor_fold_counts,
    "survivor_lofo_complete": False,
}, indent=2))
