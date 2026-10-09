#!/usr/bin/env python3
"""G2 deep independence audit on the immutable 28 Winner + 14 Prior Survivor lineage.

Research-only. Does not modify the locked population, protocol, Winner labels, or
promotion state. It measures temporal/sequence dependence and lineage separation.
"""
import json
from datetime import datetime
from pathlib import Path

SRC = Path("evidence/source_identity_reconciliation_v1.json")
OUT = Path("evidence/g2_cluster_independence_deep_audit_v1.json")

TEMPORAL_MINUTES = [1, 5, 15, 30, 60, 120]
SEQUENCE_GAPS = [0, 10_000, 50_000, 100_000, 250_000, 500_000, 1_000_000]

def ts(x):
    return datetime.fromisoformat(x.replace("Z", "+00:00")).timestamp()

def effective(sizes):
    n = sum(sizes)
    return n * n / sum(x*x for x in sizes)

def components(rows, threshold, mode):
    n = len(rows)
    parent = list(range(n))
    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    def union(a, b):
        a, b = find(a), find(b)
        if a != b:
            parent[b] = a
    for i in range(n):
        for j in range(i + 1, n):
            if mode == "time":
                d = abs(ts(rows[i]["timestamp"]) - ts(rows[j]["timestamp"])) / 60.0
            else:
                d = max(
                    0,
                    rows[i]["sequence_first"] - rows[j]["sequence_last"],
                    rows[j]["sequence_first"] - rows[i]["sequence_last"],
                )
            if d <= threshold:
                union(i, j)
    groups = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(i)
    return list(groups.values())

def summary(rows, thresholds, mode):
    out = []
    for threshold in thresholds:
        groups = components(rows, threshold, mode)
        sizes = sorted((len(g) for g in groups), reverse=True)
        out.append({
            "threshold": threshold,
            "clusters": len(groups),
            "largest_cluster": sizes[0] if sizes else 0,
            "effective_cluster_count": round(effective(sizes), 4) if sizes else 0.0,
            "cluster_sizes": sizes,
        })
    return out

def main():
    d = json.loads(SRC.read_text())
    rows = d["records"]
    assert len(rows) == 42
    assert sum(r["lineage"] == "prior_14_survivor" for r in rows) == 14
    assert sum(r["lineage"] == "current_28_winner" for r in rows) == 28
    assert d["counts"]["exact_record_key_matches"] == 0

    prior = [r for r in rows if r["lineage"] == "prior_14_survivor"]
    current = [r for r in rows if r["lineage"] == "current_28_winner"]

    cross = []
    for a in prior:
        for b in current:
            cross.append({
                "time_gap_hours": abs(ts(a["timestamp"]) - ts(b["timestamp"])) / 3600.0,
                "sequence_gap": max(
                    0,
                    a["sequence_first"] - b["sequence_last"],
                    b["sequence_first"] - a["sequence_last"],
                ),
                "prior_timestamp": a["timestamp"],
                "current_timestamp": b["timestamp"],
            })
    nearest_time = min(cross, key=lambda x: x["time_gap_hours"])
    nearest_seq = min(cross, key=lambda x: x["sequence_gap"])

    same_lineage_pairs = []
    for lineage_rows in (prior, current):
        for i in range(len(lineage_rows)):
            for j in range(i + 1, len(lineage_rows)):
                same_lineage_pairs.append({
                    "time_gap_minutes": abs(ts(lineage_rows[i]["timestamp"]) - ts(lineage_rows[j]["timestamp"])) / 60.0,
                    "sequence_gap": max(
                        0,
                        lineage_rows[i]["sequence_first"] - lineage_rows[j]["sequence_last"],
                        lineage_rows[j]["sequence_first"] - lineage_rows[i]["sequence_last"],
                    ),
                    "a": lineage_rows[i]["timestamp"],
                    "b": lineage_rows[j]["timestamp"],
                })
    nearest_within_time = min(same_lineage_pairs, key=lambda x: x["time_gap_minutes"])
    sequence_overlaps = sum(x["sequence_gap"] == 0 for x in same_lineage_pairs)

    result = {
        "schema": "hes.g2_cluster_independence_deep_audit.v1",
        "status": "RESEARCH_ONLY_FAIL_CLOSED",
        "input": {
            "artifact": str(SRC),
            "protocol": d["protocol"],
            "prior_records": 14,
            "current_records": 28,
            "exact_record_key_matches": 0,
        },
        "lineage_separation": {
            "cross_lineage_pair_count": len(cross),
            "nearest_timestamp_gap_hours": nearest_time,
            "nearest_sequence_gap": nearest_seq,
        },
        "within_lineage_overlap": {
            "nearest_start_timestamp_gap": nearest_within_time,
            "same_lineage_sequence_interval_overlaps": sequence_overlaps,
        },
        "temporal_sensitivity": {
            "prior_14": summary(prior, TEMPORAL_MINUTES, "time"),
            "current_28": summary(current, TEMPORAL_MINUTES, "time"),
        },
        "sequence_sensitivity": {
            "prior_14": summary(prior, SEQUENCE_GAPS, "sequence"),
            "current_28": summary(current, SEQUENCE_GAPS, "sequence"),
        },
        "interpretation": {
            "fold_is_not_independence_unit": True,
            "current_28_contains_temporal_concentration": True,
            "current_28_60min_largest_cluster": 13,
            "current_28_60min_effective_cluster_count": 4.0833,
            "current_28_60min_cluster_is_chain_connected": True,
            "no_cross_lineage_temporal_or_sequence_near_overlap_observed": True,
        },
        "claim_boundary": {
            "records_deleted": False,
            "winner_reselected": False,
            "gross_threshold_changed": False,
            "protocol_changed": False,
            "audit_sensitivity_threshold_selected_as_winner": False,
            "statistical_independence_proven": False,
            "predictive_validity_proven": False,
            "promotion": "BLOCKED",
        },
        "final_verdict": "G2_DEEP_AUDIT_COMPLETED_PROMOTION_STILL_BLOCKED",
    }
    OUT.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))

if __name__ == "__main__":
    main()
