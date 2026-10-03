import json
from pathlib import Path

LOCK = Path("evidence/formal_evidence_lock_v1.json")


def test_formal_evidence_lock_v1():
    d = json.loads(LOCK.read_text(encoding="utf-8"))
    assert d["artifact"] == "HES Trade Agent — Formal Evidence Lock v1"
    assert d["status"] == "EVIDENCE_LOCKED"

    gate = d["gate"]
    assert gate["workflow_run_id"] == 36998216883
    assert gate["workflow_job_id"] == 110809693633
    assert gate["workflow_conclusion"] == "success"
    assert gate["test_result"] == "1 passed"

    src = d["source"]
    assert src["source_pr"] == 129
    assert src["source_head_commit"] == "4553af53df047674ea030477ff978fd199e7787c"
    assert src["immutable_workflow_run"] == 36773191085
    assert src["immutable_artifact_id"] == 11162212837
    assert src["immutable_artifact_sha256"] == "8583c134d23eadbb3055ed373bc9024fc4605ad3449fc1808b7ddbb6576e626f"
    assert len(src["immutable_artifact_sha256"]) == 64

    pop = d["population"]
    assert pop["evaluated_observations"] == 1049
    assert pop["fold_count"] == 8
    assert pop["fold_evaluated"] == [120, 132, 135, 137, 138, 127, 126, 134]
    assert sum(pop["fold_evaluated"]) == 1049

    gap = d["gap"]
    assert gap["affected_folds"] == [7]
    assert gap["excluded_observation_count"] == 0
    assert gap["observation_coverage_loss_pct"] == 0.0
    assert gap["synthetic_fill"] is False
    assert gap["replacement_rows"] is False
    assert gap["causal_reassignment"] is False

    safety = d["safety"]
    assert all(safety.values()) is True
