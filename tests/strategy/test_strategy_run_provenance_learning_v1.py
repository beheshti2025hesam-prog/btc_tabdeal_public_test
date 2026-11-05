import json
from datetime import datetime, timedelta, timezone
from forward.strategy_v2_run_provenance_v1 import SOURCE_PATHS, append_run_manifest, create_run_manifest
import scripts.run_strategy_learning_loop_v1 as learning

def make_manifest(tmp_path):
    code=tmp_path/"release-learning"
    for relative in SOURCE_PATHS.values():
        path=code/relative; path.parent.mkdir(parents=True,exist_ok=True); path.write_text(relative)
    return create_run_manifest(root=code,service_name="strategy_policy_v2_forward_evaluator",
        policy_version="v2-test",run_id="HESV2-learning-test-0001")

def test_learning_verifies_report_to_immutable_run_manifest(tmp_path,monkeypatch):
    data=tmp_path/"data/forward"; data.mkdir(parents=True)
    manifest=make_manifest(tmp_path)
    append_run_manifest(data/"strategy_policy_v2_runs.jsonl",manifest)
    report={"updated_at":datetime.now(timezone.utc).isoformat(),"run_id":manifest["run_id"],
            "run_manifest_sha256":manifest["run_manifest_sha256"],"code_release_id":manifest["code_release_id"],
            "source_hashes":manifest["source_hashes"],**manifest["source_hashes"]}
    (data/"strategy_policy_v2_eval_report.json").write_text(json.dumps(report))
    monkeypatch.setattr(learning,"DATA",data)
    result=learning.read_strategy_run_provenance()
    assert result["status"]=="VERIFIED" and result["fresh"] is True
    assert result["run_id"]==manifest["run_id"]

def test_learning_marks_stale_but_valid_provenance_as_stale(tmp_path,monkeypatch):
    data=tmp_path/"data/forward"; data.mkdir(parents=True)
    manifest=make_manifest(tmp_path)
    append_run_manifest(data/"strategy_policy_v2_runs.jsonl",manifest)
    report={"updated_at":(datetime.now(timezone.utc)-timedelta(hours=2)).isoformat(),
            "run_id":manifest["run_id"],"run_manifest_sha256":manifest["run_manifest_sha256"],
            "code_release_id":manifest["code_release_id"],"source_hashes":manifest["source_hashes"],**manifest["source_hashes"]}
    (data/"strategy_policy_v2_eval_report.json").write_text(json.dumps(report))
    monkeypatch.setattr(learning,"DATA",data)
    result=learning.read_strategy_run_provenance()
    assert result["status"]=="VERIFIED" and result["fresh"] is False

def test_learning_rejects_report_manifest_mismatch(tmp_path,monkeypatch):
    data=tmp_path/"data/forward"; data.mkdir(parents=True)
    manifest=make_manifest(tmp_path)
    append_run_manifest(data/"strategy_policy_v2_runs.jsonl",manifest)
    report={"updated_at":datetime.now(timezone.utc).isoformat(),"run_id":manifest["run_id"],
            "run_manifest_sha256":"0"*64,"code_release_id":manifest["code_release_id"],
            "source_hashes":manifest["source_hashes"],**manifest["source_hashes"]}
    (data/"strategy_policy_v2_eval_report.json").write_text(json.dumps(report))
    monkeypatch.setattr(learning,"DATA",data)
    assert learning.read_strategy_run_provenance()["status"]=="RUN_MANIFEST_REPORT_MISMATCH"
