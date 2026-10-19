import json
from pathlib import Path


EVIDENCE = Path("evidence/evidence_lock_gate_v1.json")


def test_evidence_lock_gate_v1():
    d = json.loads(EVIDENCE.read_text(encoding="utf-8"))

    assert d["status"] == "EVIDENCE_LOCK_READY"

    lineage = d["lineage"]
    assert lineage["source_head_commit"] == "4553af53df047674ea030477ff978fd199e7787c"
    assert lineage["immutable_workflow_run"] == 36773191085
    assert lineage["workflow_run_number"] == 181
    assert lineage["immutable_artifact_id"] == 11162212837
    assert lineage["immutable_artifact_sha256"] == "8583c134d23eadbb3055ed373bc9024fc4605ad3449fc1808b7ddbb6576e626f"
    assert lineage["exact_1049_replay"] is True
    assert lineage["exact_match_to_locked_evidence"] is True

    pop = d["locked_population"]
    folds = pop["fold_evaluated"]
    assert pop["evaluated_observations"] == 1049
    assert pop["fold_count"] == 8
    assert folds == [120, 132, 135, 137, 138, 127, 126, 134]
    assert sum(folds) == 1049
    assert pop["fold_sum_check"] == 1049
    assert pop["wins"] + pop["losses"] + pop["unlabeled_evaluated"] == 1049

    gap = d["gap_boundary"]
    assert gap["affected_folds"] == [7]
    assert gap["start"] == "2026-09-27T12:03:19.239Z"
    assert gap["end"] == "2026-09-27T17:16:54.102Z"
    assert gap["duration_seconds"] == 18814.863
    assert gap["duration_hours"] == 5.226350833333333
    assert gap["fold7_window_hours"] == 16.583333333333334

    cov = d["coverage_assertions"]
    assert cov["excluded_observation_ids"] == []
    assert cov["excluded_observation_count"] == 0
    assert cov["evaluated_observations_removed_by_gap"] == 0
    assert cov["locked_population_before"] == 1049
    assert cov["locked_population_after_gap_exclusion"] == 1049
    assert cov["observation_delta"] == 0
    assert cov["observation_coverage_loss_pct"] == 0.0
    assert cov["raw_time_coverage_delta_hours"] == -5.226350833333333
    assert cov["gap_preserved"] is True
    assert cov["no_causal_reassignment"] is True

    mapping = d["fold_mapping_assertions"]
    assert list(mapping) == [f"fold{i}" for i in range(8)]
    for i, expected in enumerate(folds):
        row = mapping[f"fold{i}"]
        assert row["evaluated"] == expected
        assert row["excluded_observations"] == 0
        assert row["coverage_delta_pct"] == 0.0
        assert row["gap_intersects"] is (i == 7)

    synth = d["synthetic_fill_assertion"]
    assert synth["synthetic_rows_added"] is False
    assert synth["synthetic_fill"] is False
    assert synth["replacement_rows_created"] is False
    assert synth["raw_lineage_recovery_method"] == "immutable Git checkpoints / workflow artifact only"

    integrity = d["integrity_assertions"]
    assert all(integrity.values()) is True

    safety = d["safety"]
    assert safety["main_untouched"] is True
    assert safety["data_engine_v1_untouched"] is True
    assert safety["live_execution_disabled"] is True
    assert safety["promotion_disabled"] is True
    assert safety["pr_129_unmerged"] is True
