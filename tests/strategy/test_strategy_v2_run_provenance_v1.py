import json
from datetime import datetime, timezone
from pathlib import Path
import pytest

from forward.strategy_v2_run_provenance_v1 import (
    SOURCE_PATHS, append_run_manifest, create_run_manifest, validate_run_manifest,
)

def make_code_root(tmp_path):
    root=tmp_path/"release-abc123"
    for relative in SOURCE_PATHS.values():
        path=root/relative
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text("fixture:"+relative,encoding="utf-8")
    return root

def test_manifest_pins_full_strategy_journal_and_learning_code_chain(tmp_path):
    root=make_code_root(tmp_path)
    manifest=create_run_manifest(root=root,service_name="strategy_policy_v2_forward_evaluator",
        policy_version="v2-test",run_id="HESV2-test-run-0001")
    assert manifest["code_release_id"]==root.name
    assert manifest["service_name"]=="strategy_policy_v2_forward_evaluator"
    assert set(manifest["source_hashes"])==set(SOURCE_PATHS)
    assert all(len(value)==64 for value in manifest["source_hashes"].values())
    assert validate_run_manifest(manifest)
    assert manifest["execution_enabled"] is False and manifest["orders_placed"] is False

def test_manifest_append_is_idempotency_guarded_and_hash_validated(tmp_path):
    root=make_code_root(tmp_path)
    manifest=create_run_manifest(root=root,service_name="strategy_policy_v2_forward_evaluator",
        policy_version="v2-test",run_id="HESV2-test-run-0002")
    target=tmp_path/"runs.jsonl"
    append_run_manifest(target,manifest)
    rows=[json.loads(line) for line in target.read_text().splitlines()]
    assert len(rows)==1 and rows[0]==manifest
    with pytest.raises(ValueError,match="duplicate Strategy V2 run_id"):
        append_run_manifest(target,manifest)
    changed=dict(manifest); changed["strategy_source_sha256"]="0"*64
    assert not validate_run_manifest(changed)
    with pytest.raises(ValueError,match="invalid Strategy V2 run manifest digest"):
        append_run_manifest(tmp_path/"bad.jsonl",changed)

def test_evaluator_initializes_run_manifest_from_immutable_code_root(tmp_path,monkeypatch):
    import scripts.run_strategy_policy_v2_forward_eval as evaluator
    code_root=make_code_root(tmp_path)
    data_root=tmp_path/"shared-data"
    monkeypatch.setattr(evaluator,"CODE_ROOT",code_root)
    monkeypatch.setattr(evaluator,"RUN_MANIFEST",data_root/"strategy_policy_v2_runs.jsonl")
    monkeypatch.setattr(evaluator,"RUN_PROVENANCE",None)
    manifest=evaluator.initialize_run_provenance()
    assert manifest["code_release_id"]==code_root.name
    assert manifest["run_id"].startswith("HESV2-")
    assert evaluator.provenance_fields()["run_manifest_sha256"]==manifest["run_manifest_sha256"]
    saved=json.loads(evaluator.RUN_MANIFEST.read_text().splitlines()[0])
    assert saved==manifest
    source=(code_root/"scripts/run_strategy_policy_v2_forward_eval.py")
    source.parent.mkdir(parents=True,exist_ok=True)
    source.write_text("assert initialization happens before the loop")
    script=(Path(evaluator.__file__).read_text())
    assert script.index("initialize_run_provenance()") < script.index("while True:")


def test_source_map_matches_and_hashes_the_real_repository_layout():
    repository_root=Path(__file__).resolve().parents[2]
    missing=[relative for relative in SOURCE_PATHS.values() if not (repository_root/relative).is_file()]
    assert missing == []
    manifest=create_run_manifest(root=repository_root,service_name="strategy_policy_v2_forward_evaluator",
        policy_version="repository-layout-smoke",run_id="HESV2-repository-layout-0001")
    assert validate_run_manifest(manifest)
    assert len(manifest["source_hashes"])==len(SOURCE_PATHS)
