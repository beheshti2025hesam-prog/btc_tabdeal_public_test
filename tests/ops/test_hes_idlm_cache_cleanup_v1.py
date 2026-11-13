from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

import scripts.ops.hes_idlm_cache_cleanup_v1 as cleanup


def _old_tree(path: Path, now: datetime, *, file_name="module.pyc"):
    path.mkdir(parents=True)
    file_path = path / file_name
    file_path.write_bytes(b"regenerable-cache")
    old = (now - timedelta(days=15)).timestamp()
    os.utime(file_path, (old, old))
    os.utime(path, (old, old))
    return file_path


def _plan(monkeypatch, tmp_path, now, *, registered=None, registry_error=None, proc_root=None):
    monkeypatch.setattr(cleanup, "ALLOWED_ROOTS", (tmp_path,))
    proc = proc_root or tmp_path / "proc"
    proc.mkdir(parents=True, exist_ok=True)
    return cleanup.build_cleanup_plan(
        now=now,
        registered_worktrees=registered if registered is not None else set(),
        worktree_registry_error=registry_error,
        proc_root=proc,
    )


def test_old_allowlisted_cache_is_dry_run_candidate(monkeypatch, tmp_path):
    now = datetime.now(timezone.utc) + timedelta(days=15)
    cache = tmp_path / "run-a" / "__pycache__"
    _old_tree(cache, now)
    (tmp_path / "proc").mkdir()

    plan = _plan(monkeypatch, tmp_path, now)

    row = next(item for item in plan["candidates"] if item["path"] == str(cache))
    assert row["eligible"] is True
    assert row["reason"] == "ALLOWLISTED_OLD_CACHE_NO_REFERENCES"
    assert row["tree_sha256"]
    assert row["automatic_action"] == "NONE"
    assert plan["execution_enabled"] is False
    assert plan["deletion_authorized"] is False


def test_only_exact_cache_names_are_considered(monkeypatch, tmp_path):
    now = datetime.now(timezone.utc) + timedelta(days=15)
    old = tmp_path / "run-a" / "scratch"
    _old_tree(old, now)
    (tmp_path / "proc").mkdir()

    plan = _plan(monkeypatch, tmp_path, now)

    assert plan["candidates"] == []


def test_recent_file_blocks_entire_cache(monkeypatch, tmp_path):
    now = datetime.now(timezone.utc) + timedelta(days=15)
    cache = tmp_path / "run-a" / ".pytest_cache"
    file_path = _old_tree(cache, now)
    recent = cache / "recent"
    recent.write_text("active")
    os.utime(recent, (now.timestamp(), now.timestamp()))
    old = (now - timedelta(days=15)).timestamp()
    os.utime(cache, (old, old))
    plan = _plan(monkeypatch, tmp_path, now)

    row = next(item for item in plan["candidates"] if item["path"] == str(cache))
    assert row["eligible"] is False
    assert row["reason"] == "RECENT_ENTRY_PRESENT"


def test_backdated_file_with_recent_ctime_blocks_entire_cache(monkeypatch, tmp_path):
    now = datetime.now(timezone.utc) + timedelta(days=15)
    cache = tmp_path / "run-a" / "__pycache__"
    _old_tree(cache, now)
    original_snapshot = cleanup._tree_snapshot

    def snapshot_with_recent_ctime(path):
        snapshot, identities = original_snapshot(path)
        for entry in snapshot["entries"]:
            if entry["kind"] == "file":
                entry["ctime_ns"] = int((now - timedelta(days=1)).timestamp() * 1_000_000_000)
        return snapshot, identities

    monkeypatch.setattr(cleanup, "_tree_snapshot", snapshot_with_recent_ctime)
    plan = _plan(monkeypatch, tmp_path, now)

    row = next(item for item in plan["candidates"] if item["path"] == str(cache))
    assert row["eligible"] is False
    assert row["reason"] == "RECENT_ENTRY_PRESENT"


def test_symlink_inside_cache_blocks_candidate(monkeypatch, tmp_path):
    now = datetime.now(timezone.utc) + timedelta(days=15)
    cache = tmp_path / "run-a" / "__pycache__"
    file_path = _old_tree(cache, now)
    outside = tmp_path / "outside"
    outside.write_text("do not follow")
    (cache / "link").symlink_to(outside)
    old = (now - timedelta(days=15)).timestamp()
    os.utime(cache, (old, old))
    (tmp_path / "proc").mkdir()

    plan = _plan(monkeypatch, tmp_path, now)
    row = next(item for item in plan["candidates"] if item["path"] == str(cache))
    assert row["eligible"] is False
    assert row["reason"] == "SYMLINK_PRESENT"


def test_hardlinked_file_blocks_candidate(monkeypatch, tmp_path):
    now = datetime.now(timezone.utc) + timedelta(days=15)
    cache = tmp_path / "run-a" / "__pycache__"
    file_path = _old_tree(cache, now)
    os.link(file_path, tmp_path / "outside-hardlink")
    (tmp_path / "proc").mkdir()

    plan = _plan(monkeypatch, tmp_path, now)
    row = next(item for item in plan["candidates"] if item["path"] == str(cache))
    assert row["eligible"] is False
    assert row["reason"] == "HARDLINK_PRESENT"


def test_registered_worktree_cache_is_not_discovered(monkeypatch, tmp_path):
    now = datetime.now(timezone.utc) + timedelta(days=15)
    worktree = tmp_path / "worktree"
    cache = worktree / "__pycache__"
    _old_tree(cache, now)
    (tmp_path / "proc").mkdir()

    plan = _plan(monkeypatch, tmp_path, now, registered={worktree})
    assert plan["candidates"] == []


def test_unavailable_worktree_registry_fails_closed(monkeypatch, tmp_path):
    now = datetime.now(timezone.utc) + timedelta(days=15)
    cache = tmp_path / "run-a" / "__pycache__"
    _old_tree(cache, now)
    (tmp_path / "proc").mkdir()

    plan = _plan(
        monkeypatch, tmp_path, now, registered=set(),
        registry_error="git_registry_unavailable",
    )
    assert plan["candidates"] == []
    assert "WORKTREE_REGISTRY_UNAVAILABLE" in plan["scan_errors"]
    assert plan["eligible_count"] == 0


def test_open_process_file_descriptor_blocks_candidate(monkeypatch, tmp_path):
    now = datetime.now(timezone.utc) + timedelta(days=15)
    cache = tmp_path / "run-a" / "__pycache__"
    file_path = _old_tree(cache, now)
    proc = tmp_path / "proc"
    fd_dir = proc / "123" / "fd"
    fd_dir.mkdir(parents=True)
    (fd_dir / "7").symlink_to(file_path)
    plan = _plan(monkeypatch, tmp_path, now, proc_root=proc)

    row = next(item for item in plan["candidates"] if item["path"] == str(cache))
    assert row["eligible"] is False
    assert row["reason"] == "OPEN_PROCESS_REFERENCE"


def test_quarantine_restore_path_contract_is_narrow():
    assert cleanup.CONFIRM_PHRASE == "QUARANTINE HES TEMP CACHES"
    assert cleanup.MIN_AGE_DAYS == 14
    assert cleanup.ALLOWED_NAMES == {"__pycache__", ".pytest_cache"}
    assert cleanup.MAX_CANDIDATES <= 10



def test_open_current_working_directory_blocks_candidate(monkeypatch, tmp_path):
    now = datetime.now(timezone.utc) + timedelta(days=15)
    cache = tmp_path / "run-a" / "__pycache__"
    _old_tree(cache, now)
    proc = tmp_path / "proc"
    cwd = proc / "321"
    cwd.mkdir(parents=True)
    (cwd / "cwd").symlink_to(cache, target_is_directory=True)

    plan = _plan(monkeypatch, tmp_path, now, proc_root=proc)

    row = next(item for item in plan["candidates"] if item["path"] == str(cache))
    assert row["eligible"] is False
    assert row["reason"] == "OPEN_PROCESS_REFERENCE"


def test_memory_mapping_blocks_candidate(tmp_path):
    cache = tmp_path / "cache" / "__pycache__"
    cache.parent.mkdir()
    file_path = _old_tree(cache, datetime.now(timezone.utc))
    st = file_path.stat()
    proc = tmp_path / "proc"
    maps = proc / "456" / "maps"
    maps.parent.mkdir(parents=True)
    device = f"{os.major(st.st_dev):02x}:{os.minor(st.st_dev):02x}"
    maps.write_text(f"1000-2000 rw-p 00000000 {device} {st.st_ino} {file_path}\n")

    _, identities = cleanup._tree_snapshot(cache)
    refs, errors = cleanup._open_reference_scan(identities, proc_root=proc)

    assert errors == []
    assert any(ref.get("mapping") == str(file_path) for ref in refs)


def test_tree_entry_limit_fails_closed(monkeypatch, tmp_path):
    cache = tmp_path / "cache" / ".pytest_cache"
    _old_tree(cache, datetime.now(timezone.utc))
    monkeypatch.setattr(cleanup, "MAX_TREE_ENTRIES", 1)

    try:
        cleanup._tree_snapshot(cache)
    except cleanup.CleanupSafetyError as exc:
        assert str(exc) == "TREE_ENTRY_LIMIT"
    else:
        raise AssertionError("large tree must fail closed")



def test_apply_requires_explicit_phrase_even_for_root(monkeypatch, tmp_path):
    from datetime import datetime
    import json

    monkeypatch.setattr(cleanup.os, "geteuid", lambda: 0)
    manifest_path = tmp_path / "plan.json"
    manifest_path.write_text(json.dumps({
        "schema": "hes_idlm_cache_cleanup_plan_v1",
        "policy_version": cleanup.POLICY_VERSION,
    }))
    try:
        cleanup.quarantine_manifest(
            manifest_path,
            expected_sha256=cleanup._manifest_digest(manifest_path),
            confirmation="",
        )
    except cleanup.CleanupSafetyError as exc:
        assert str(exc) == "EXPLICIT_CONFIRMATION_REQUIRED"
    else:
        raise AssertionError("apply must require explicit typed confirmation")



def test_dry_run_manifest_creation_is_exclusive_and_private(tmp_path):
    import stat

    target = tmp_path / "plan.json"
    digest = cleanup._write_new_manifest(target, '{"action":"NONE"}\n')

    assert digest == cleanup._manifest_digest(target)
    assert stat.S_IMODE(target.stat().st_mode) == 0o600
    try:
        cleanup._write_new_manifest(target, '{"overwritten":true}\n')
    except FileExistsError:
        pass
    else:
        raise AssertionError("dry-run output must never overwrite an existing file")
    assert target.read_text() == '{"action":"NONE"}\n'


def test_directory_chain_open_rejects_symlink_component(tmp_path):
    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "link"
    link.symlink_to(real, target_is_directory=True)

    try:
        cleanup._open_directory_chain(link)
    except OSError:
        pass
    else:
        raise AssertionError("directory descriptor walk must reject symlink components")



def test_restore_identity_scan_preserves_symlinks_without_following(tmp_path):
    cache = tmp_path / "quarantine" / "__pycache__"
    cache.mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.write_text("outside")
    link = cache / "link"
    link.symlink_to(outside)

    identities = cleanup._restore_identity_scan(cache)

    link_stat = link.lstat()
    outside_stat = outside.stat()
    assert (link_stat.st_dev, link_stat.st_ino) in identities
    assert (outside_stat.st_dev, outside_stat.st_ino) not in identities



def test_atomic_noreplace_rename_preserves_existing_destination(tmp_path):
    source_dir = tmp_path / "source"
    destination_dir = tmp_path / "destination"
    source_dir.mkdir()
    destination_dir.mkdir()
    (source_dir / "cache").mkdir()
    (destination_dir / "cache").mkdir()
    (destination_dir / "cache" / "keep.txt").write_text("keep")

    source_fd = cleanup._open_directory_chain(source_dir)
    destination_fd = cleanup._open_directory_chain(destination_dir)
    try:
        try:
            cleanup._rename_noreplace(
                "cache", "cache",
                source_dir_fd=source_fd, destination_dir_fd=destination_fd,
            )
        except FileExistsError:
            pass
        else:
            raise AssertionError("rename must not overwrite an existing destination")
        assert (destination_dir / "cache" / "keep.txt").read_text() == "keep"
        assert (source_dir / "cache").is_dir()
    finally:
        os.close(source_fd)
        os.close(destination_fd)


def test_atomic_noreplace_rename_moves_directory_when_destination_absent(tmp_path):
    source_dir = tmp_path / "source"
    destination_dir = tmp_path / "destination"
    source_dir.mkdir()
    destination_dir.mkdir()
    (source_dir / "cache").mkdir()
    (source_dir / "cache" / "file").write_text("preserve")

    source_fd = cleanup._open_directory_chain(source_dir)
    destination_fd = cleanup._open_directory_chain(destination_dir)
    try:
        cleanup._rename_noreplace(
            "cache", "moved-cache",
            source_dir_fd=source_fd, destination_dir_fd=destination_fd,
        )
    finally:
        os.close(source_fd)
        os.close(destination_fd)

    assert not (source_dir / "cache").exists()
    assert (destination_dir / "moved-cache" / "file").read_text() == "preserve"



def test_tree_fingerprint_is_stable_across_directory_rename(tmp_path):
    source = tmp_path / "source" / "__pycache__"
    source.mkdir(parents=True)
    file_path = source / "module.pyc"
    file_path.write_bytes(b"stable")
    before, _ = cleanup._tree_snapshot(source)

    destination = tmp_path / "destination"
    os.rename(source, destination)

    after, _ = cleanup._tree_snapshot(destination)
    assert before["tree_sha256"] == after["tree_sha256"]


def test_end_to_end_quarantine_and_restore_with_root_privilege(tmp_path):
    if os.geteuid() != 0:
        if shutil.which("sudo") is None:
            pytest.skip("root or passwordless sudo is required for end-to-end safety test")
        probe = subprocess.run(["sudo", "-n", "true"], capture_output=True)
        if probe.returncode != 0:
            pytest.skip("passwordless sudo is unavailable")

    script = r"""
import hashlib
import json
import os
import shutil
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
import scripts.ops.hes_idlm_cache_cleanup_v1 as cleanup

def run(base):
    cleanup.ALLOWED_ROOTS = (base,)
    cleanup.REPO_ROOT = base
    cleanup._load_worktrees = lambda _root: (set(), None)
    proc_root = base / "proc"
    proc_root.mkdir()
    target = base / "fixture" / "__pycache__"
    target.mkdir(parents=True)
    cached_file = target / "module.pyc"
    cached_file.write_bytes(b"end-to-end-cache")
    now = datetime.now(timezone.utc) + timedelta(days=15)
    old = (now - timedelta(days=15)).timestamp()
    os.utime(cached_file, (old, old))
    os.utime(target, (old, old))
    original_build_cleanup_plan = cleanup.build_cleanup_plan
    def build_cleanup_plan_with_test_clock(*args, **kwargs):
        kwargs.setdefault("now", now)
        return original_build_cleanup_plan(*args, **kwargs)
    cleanup.build_cleanup_plan = build_cleanup_plan_with_test_clock
    plan = cleanup.build_cleanup_plan(
        now=now, registered_worktrees=set(), proc_root=proc_root
    )
    assert plan["eligible_count"] == 1, plan
    manifest_path = base / "plan.json"
    manifest_bytes = (json.dumps(plan, sort_keys=True) + "\n").encode()
    manifest_path.write_bytes(manifest_bytes)
    os.chmod(manifest_path, 0o600)
    digest = hashlib.sha256(manifest_bytes).hexdigest()
    audit_path = base / "audit" / "cleanup.jsonl"
    actions = cleanup.quarantine_manifest(
        manifest_path,
        expected_sha256=digest,
        confirmation=cleanup.CONFIRM_PHRASE,
        audit_path=audit_path,
        proc_root=proc_root,
    )
    assert len(actions) == 1
    quarantined = Path(actions[0]["destination"])
    assert quarantined.is_dir() and not target.exists()
    result = cleanup.restore_quarantine(
        quarantined,
        confirmation="RESTORE HES QUARANTINED CACHE",
        audit_path=audit_path,
    )
    assert result["action"] == "RESTORED"
    assert (target / "module.pyc").read_bytes() == b"end-to-end-cache"
    assert not quarantined.exists()

base = Path(sys.argv[1]) / "root-test"
base.mkdir(mode=0o700)
try:
    run(base)
    print("IDLM_QUARANTINE_RESTORE_E2E=PASS")
finally:
    shutil.rmtree(base, ignore_errors=True)
"""
    command = [sys.executable, "-c", script, str(tmp_path)]
    if os.geteuid() != 0:
        command = ["sudo", "-n", *command]
    result = subprocess.run(command, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + "\n" + result.stderr
    assert "IDLM_QUARANTINE_RESTORE_E2E=PASS" in result.stdout



def test_apply_time_scan_errors_block_quarantine():
    from scripts.ops.hes_idlm_cache_cleanup_v1 import _require_complete_fresh_scan, CleanupSafetyError

    with pytest.raises(CleanupSafetyError, match="FRESH_SCAN_INCOMPLETE"):
        _require_complete_fresh_scan({"scan_errors": ["UNREADABLE_ROOT"], "worktree_registry": {"error": None}})
    with pytest.raises(CleanupSafetyError, match="FRESH_SCAN_INCOMPLETE"):
        _require_complete_fresh_scan({"scan_errors": [], "worktree_registry": {"error": "REGISTRY_UNAVAILABLE"}})
    _require_complete_fresh_scan({"scan_errors": [], "worktree_registry": {"error": None}})


def test_content_changed_quarantine_event_remains_restorable():
    from scripts.ops.hes_idlm_cache_cleanup_v1 import _restorable_quarantine_event

    assert _restorable_quarantine_event("QUARANTINE_CONTENT_CHANGED") is True
    assert _restorable_quarantine_event("QUARANTINE_HELD") is True
    assert _restorable_quarantine_event("QUARANTINED") is True
    assert _restorable_quarantine_event("QUARANTINE_ABORTED") is False
    assert _restorable_quarantine_event("QUARANTINE_IDENTITY_MISMATCH") is False



def test_content_changed_during_quarantine_can_be_restored_with_contents_preserved(tmp_path):
    if os.geteuid() != 0:
        if shutil.which("sudo") is None or subprocess.run(["sudo", "-n", "true"], capture_output=True).returncode != 0:
            pytest.skip("root or passwordless sudo is required for end-to-end safety test")
    script = r"""
import hashlib, json, os, shutil, sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
import scripts.ops.hes_idlm_cache_cleanup_v1 as cleanup

def run(base):
    cleanup.ALLOWED_ROOTS = (base,)
    cleanup.REPO_ROOT = base
    cleanup._load_worktrees = lambda _root: (set(), None)
    proc_root = base / "proc"
    proc_root.mkdir()
    target = base / "fixture" / "__pycache__"
    target.mkdir(parents=True)
    cached_file = target / "module.pyc"
    cached_file.write_bytes(b"before-move")
    now = datetime.now(timezone.utc) + timedelta(days=15)
    old = (now - timedelta(days=15)).timestamp()
    os.utime(cached_file, (old, old)); os.utime(target, (old, old))
    original_build = cleanup.build_cleanup_plan
    def build_with_clock(*args, **kwargs):
        kwargs.setdefault("now", now)
        return original_build(*args, **kwargs)
    cleanup.build_cleanup_plan = build_with_clock
    plan = cleanup.build_cleanup_plan(now=now, registered_worktrees=set(), proc_root=proc_root)
    assert plan["eligible_count"] == 1, plan
    manifest_path = base / "plan.json"
    manifest_bytes = (json.dumps(plan, sort_keys=True) + "\n").encode()
    manifest_path.write_bytes(manifest_bytes); os.chmod(manifest_path, 0o600)
    digest = hashlib.sha256(manifest_bytes).hexdigest()
    audit_path = base / "audit" / "cleanup.jsonl"
    original_snapshot = cleanup._tree_snapshot
    def mutate_only_after_rename(path):
        path = Path(path)
        if path.parent.parent.name == cleanup.QUARANTINE_NAME:
            (path / "module.pyc").write_bytes(b"changed-during-rename-window")
        return original_snapshot(path)
    cleanup._tree_snapshot = mutate_only_after_rename
    try:
        cleanup.quarantine_manifest(manifest_path, expected_sha256=digest,
            confirmation=cleanup.CONFIRM_PHRASE, audit_path=audit_path, proc_root=proc_root)
        raise AssertionError("content mutation during rename window was not detected")
    except cleanup.CleanupSafetyError as exc:
        assert str(exc) == "POST_RENAME_CONTENT_CHANGED_RESTORE_AVAILABLE", str(exc)
    cleanup._tree_snapshot = original_snapshot
    events = [json.loads(line) for line in audit_path.read_text().splitlines()]
    event = next(row for row in reversed(events) if row["action"] == "QUARANTINE_CONTENT_CHANGED")
    quarantined = Path(event["destination"])
    assert quarantined.is_dir() and not target.exists()
    result = cleanup.restore_quarantine(quarantined,
        confirmation="RESTORE HES QUARANTINED CACHE", audit_path=audit_path)
    assert result["action"] == "RESTORED"
    assert (target / "module.pyc").read_bytes() == b"changed-during-rename-window"
    assert not quarantined.exists()

base = Path(sys.argv[1]) / "root-test"
base.mkdir(mode=0o700)
try:
    run(base)
    print("IDLM_CONTENT_CHANGED_RESTORE_E2E=PASS")
finally:
    shutil.rmtree(base, ignore_errors=True)
"""
    command = [sys.executable, "-c", script, str(tmp_path)]
    if os.geteuid() != 0:
        command = ["sudo", "-n", *command]
    result = subprocess.run(command, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + "\\n" + result.stderr
    assert "IDLM_CONTENT_CHANGED_RESTORE_E2E=PASS" in result.stdout
