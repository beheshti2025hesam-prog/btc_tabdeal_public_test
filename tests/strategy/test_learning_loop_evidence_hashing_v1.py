import hashlib
from pathlib import Path

from scripts.run_strategy_learning_loop_v1 import sha


def test_non_jsonl_evidence_uses_raw_sha_without_sidecar_lock(tmp_path: Path):
    path = tmp_path / "report.json"
    payload = bytes.fromhex("7b22736368656d61223a2266697874757265227d0a")
    path.write_bytes(payload)
    assert sha(path) == hashlib.sha256(payload).hexdigest()
    assert not path.with_name(path.name + ".lock").exists()


def test_jsonl_evidence_uses_logical_hash(tmp_path: Path):
    path = tmp_path / "journal.jsonl"
    payload = bytes.fromhex("7b226576656e745f6964223a226531227d0a")
    path.write_bytes(payload)
    assert sha(path) == hashlib.sha256(payload).hexdigest()
    assert path.with_name(path.name + ".lock").exists()


def test_has_sealed_segments_probe_does_not_create_locks_for_non_jsonl_or_missing_jsonl(tmp_path: Path):
    from forward.sealed_jsonl_segments_v1 import has_sealed_segments

    report = tmp_path / "report.json"
    missing = tmp_path / "missing.jsonl"
    assert not has_sealed_segments(report)
    assert not has_sealed_segments(missing)
    assert not report.with_name(report.name + ".lock").exists()
    assert not missing.with_name(missing.name + ".lock").exists()