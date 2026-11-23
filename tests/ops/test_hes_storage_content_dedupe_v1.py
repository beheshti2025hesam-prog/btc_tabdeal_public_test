from datetime import datetime, timezone
import os
from pathlib import Path
import stat

from scripts.ops.hes_storage_content_dedupe_v1 import plan_dedupe, apply_dedupe

NOW = datetime(2026, 11, 23, 12, 0, tzinfo=timezone.utc)


def snapshot(root: Path, name: str) -> Path:
    path = root / name
    path.mkdir(parents=True)
    return path


def test_dry_run_detects_only_exact_eligible_duplicates(tmp_path):
    root = tmp_path / "recovery-metadata"
    root.mkdir()
    a = snapshot(root, "differential-v2-20261122T120000Z")
    b = snapshot(root, "differential-v2-20261122T130000Z")
    c = snapshot(root, "failed-builds")
    p1 = a / "payload.tar"
    p2 = b / "payload.tar"
    p1.write_bytes(b"x" * (2 * 1024 * 1024))
    p2.write_bytes(b"x" * (2 * 1024 * 1024))
    (c / "payload.tar").write_bytes(b"x" * (2 * 1024 * 1024))
    os.chmod(p1, 0o600)
    os.chmod(p2, 0o600)
    os.utime(p1, ns=(int(NOW.timestamp() * 1_000_000_000) - 100_000_000_000, int(NOW.timestamp() * 1_000_000_000) - 100_000_000_000))
    os.utime(p2, ns=(int(NOW.timestamp() * 1_000_000_000) - 90_000_000_000, int(NOW.timestamp() * 1_000_000_000) - 90_000_000_000))
    plan = plan_dedupe(root, now=NOW, min_age_seconds=3600, open_inode_set=set())
    assert plan["duplicate_group_count"] == 1
    assert plan["duplicate_path_count"] == 1
    assert plan["potential_saved_bytes"] == p2.stat().st_blocks * 512
    assert p1.stat().st_ino != p2.stat().st_ino


def test_apply_preserves_paths_content_and_original_metadata_in_manifest(tmp_path):
    root = tmp_path / "recovery-metadata"
    root.mkdir()
    a = snapshot(root, "differential-v2-20261122T120000Z")
    b = snapshot(root, "differential-v2-20261122T130000Z")
    payload = b"same backup payload" * 100000
    p1, p2 = a / "payload.tar", b / "payload.tar"
    p1.write_bytes(payload)
    p2.write_bytes(payload)
    os.chmod(p1, 0o600)
    os.chmod(p2, 0o600)
    original_mtime = p2.stat().st_mtime_ns
    plan = plan_dedupe(root, now=NOW, min_age_seconds=0, open_inode_set=set())
    manifest = apply_dedupe(plan, tmp_path / "evidence" / "dedupe.json")
    assert manifest["status"] == "APPLIED"
    assert p1.exists() and p2.exists()
    assert p1.read_bytes() == payload and p2.read_bytes() == payload
    assert p1.stat().st_ino == p2.stat().st_ino
    assert manifest["linked_paths"][0]["original_mtime_ns"] == original_mtime
    assert manifest["linked_path_count"] == 1


def test_mode_mismatch_is_not_deduplicated(tmp_path):
    root = tmp_path / "recovery-metadata"
    root.mkdir()
    a = snapshot(root, "differential-v2-20261122T120000Z")
    b = snapshot(root, "differential-v2-20261122T130000Z")
    p1, p2 = a / "payload", b / "payload"
    p1.write_bytes(b"z" * (2 * 1024 * 1024))
    p2.write_bytes(b"z" * (2 * 1024 * 1024))
    os.chmod(p1, 0o600)
    os.chmod(p2, 0o644)
    plan = plan_dedupe(root, now=NOW, min_age_seconds=0, open_inode_set=set())
    assert plan["duplicate_group_count"] == 0


def test_open_or_already_linked_inodes_are_excluded(tmp_path):
    root = tmp_path / "recovery-metadata"
    root.mkdir()
    a = snapshot(root, "differential-v2-20261122T120000Z")
    b = snapshot(root, "differential-v2-20261122T130000Z")
    p1, p2 = a / "payload", b / "payload"
    p1.write_bytes(b"q" * (2 * 1024 * 1024))
    p2.write_bytes(b"q" * (2 * 1024 * 1024))
    plan = plan_dedupe(root, now=NOW, min_age_seconds=0, open_inode_set={(p1.stat().st_dev, p1.stat().st_ino)})
    assert plan["duplicate_group_count"] == 0


def test_unapproved_root_fails_closed(tmp_path):
    wrong = tmp_path / "other"
    wrong.mkdir()
    try:
        plan_dedupe(wrong, now=NOW, open_inode_set=set())
    except ValueError as exc:
        assert "exact HES recovery-metadata" in str(exc)
    else:
        raise AssertionError("unapproved root must fail closed")