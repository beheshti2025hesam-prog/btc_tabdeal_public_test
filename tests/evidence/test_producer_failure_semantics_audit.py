import json
from pathlib import Path

P = Path("evidence/producer_failure_semantics_audit_v1.json")

def test_producer_failure_is_explicit_but_artifact_is_distinct():
    d = json.loads(P.read_text())
    assert d["producer_run"]["workflow_conclusion"] == "failure"
    assert d["producer_run"]["collector_job_conclusion"] == "failure"
    assert d["producer_run"]["artifact_upload_step_conclusion"] == "success"
    assert d["semantic_rule"]["workflow_failure_does_not_equal_artifact_invalid"] is True

def test_locked_population_reconciles():
    d = json.loads(P.read_text())
    assert d["cross_evidence_assertions"]["evaluated_observations"] == 1049
    assert sum(d["cross_evidence_assertions"]["fold_evaluated"]) == 1049
    assert d["cross_evidence_assertions"]["wins"] == 528
    assert d["cross_evidence_assertions"]["losses"] == 479
    assert d["cross_evidence_assertions"]["unlabeled"] == 42
    assert d["cross_evidence_assertions"]["excluded_observation_count"] == 0
    assert d["cross_evidence_assertions"]["observation_coverage_loss_pct"] == 0.0

def test_gap_and_safety_are_preserved():
    d = json.loads(P.read_text())
    a = d["cross_evidence_assertions"]
    assert a["gap_fold"] == 7
    assert a["gap_duration_seconds"] == 18814.863
    assert a["synthetic_fill"] is False
    assert a["replacement_rows"] is False
    assert a["causal_reassignment"] is False
    assert a["exact_1049_replay"] is True
    s = d["safety"]
    assert all(s.values()) is True

def test_hash_chain_is_pinned():
    d = json.loads(P.read_text())
    h = d["hash_cross_check"]
    expected = {
        "evidence_lock_gate_blob_sha": "e0103b0c1953ee7c128db3757d2a728152a4d506",
        "provenance_manifest_blob_sha": "20a2343ef69c0228a3dc57974f2615a094e4efdd",
        "immutable_archive_recovery_blob_sha": "b706a7aa6c5a3ee0fd9a40307c579c007e6d72db",
        "snapshot_gap_forensics_blob_sha": "aaa6840065c74ad981865233133ac34c29f0ab1d",
        "fold_gap_impact_audit_blob_sha": "f8881b455f5e5b909564466ebce646d6a6d4d967",
        "formal_evidence_lock_blob_sha": "a79209789a6d2e72ad165d4b4f33fb4794492dcb",
        "snapshot_blob_gap_coverage_delta_blob_sha": "3fd9375ad612b09be85c573d14e6486749682c52",
        "freeze_candidate_blob_sha": "a11531c934ec4961790fe90b186931c7be3d0be4",
    }
    assert h == expected
