import json
from pathlib import Path

from tools.snapshot_manifest_integrity import build_manifest, load_snapshot


SNAPSHOT = Path("evidence/1049_observation_raw_lineage_snapshot_v1.json")


def test_materialized_snapshot_is_structurally_integral_and_not_mislabeled():
    data, raw = load_snapshot(SNAPSHOT)
    manifest = build_manifest(data, raw, str(SNAPSHOT))

    assert manifest["status"] == "PASS"
    assert manifest["snapshot"]["observation_count"] == 163
    assert manifest["snapshot"]["fold_counts"] == {"6": 29, "7": 134}
    assert manifest["integrity"]["duplicate_sequence"] == 0
    assert manifest["integrity"]["sequence_backward_or_equal"] == 0
    assert manifest["integrity"]["timestamp_backward_by_sequence"] == 0
    assert manifest["integrity"]["source_lineage_ok"] is True
    assert manifest["integrity"]["replacement_rows_created"] == 0

    # Critical claim boundary: this artifact is not the locked 1,049 population.
    assert manifest["reference_population"]["exact_reference_status"] == "BLOCKED"
    assert manifest["gate_boundary"]["exact_1049_snapshot"] == "BLOCKED"
    assert manifest["gate_boundary"]["candidate_performance_study"] == "BLOCKED"
    assert manifest["gate_boundary"]["signal_research_review"] == "BLOCKED"


def test_snapshot_manifest_is_self_consistent():
    data, raw = load_snapshot(SNAPSHOT)
    manifest = build_manifest(data, raw, str(SNAPSHOT))

    assert manifest["source_lineage"]["trades_blob_sha"] == data["source"]["trades_blob_sha"]
    assert manifest["source_lineage"]["source_commit"] == data["source"]["source_commit"]
    assert manifest["snapshot"]["observation_count"] == len(data["observations"])
