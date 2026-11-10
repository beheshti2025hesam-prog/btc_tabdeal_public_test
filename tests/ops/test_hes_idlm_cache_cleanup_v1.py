from datetime import datetime, timedelta, timezone
import os
from pathlib import Path

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
    now = datetime(2026, 11, 10, tzinfo=timezone.utc)
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
    now = datetime(2026, 11, 10, tzinfo=timezone.utc)
    old = tmp_path / "run-a" / "scratch"
    _old_tree(old, now)
    (tmp_path / "proc").mkdir()

    plan = _plan(monkeypatch, tmp_path, now)

    assert plan["candidates"] == []


def test_recent_file_blocks_entire_cache(monkeypatch, tmp_path):
    now = datetime(2026, 11, 10, tzinfo=timezone.utc)
    cache = tmp_path / "run-a" / ".pytest_cache"
    file_path = _old_tree(cache, now)
    recent = cache / "recent"
    recent.write_text("active")
    old = (now - timedelta(days=15)).timestamp()
    os.utime(cache, (old, old))
    plan = _plan(monkeypatch, tmp_path, now)

    row = next(item for item in plan["candidates"] if item["path"] == str(cache))
    assert row["eligible"] is False
    assert row["reason"] == "RECENT_ENTRY_PRESENT"


def test_symlink_inside_cache_blocks_candidate(monkeypatch, tmp_path):
    now = datetime(2026, 11, 10, tzinfo=timezone.utc)
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
    now = datetime(2026, 11, 10, tzinfo=timezone.utc)
    cache = tmp_path / "run-a" / "__pycache__"
    file_path = _old_tree(cache, now)
    os.link(file_path, tmp_path / "outside-hardlink")
    (tmp_path / "proc").mkdir()

    plan = _plan(monkeypatch, tmp_path, now)
    row = next(item for item in plan["candidates"] if item["path"] == str(cache))
    assert row["eligible"] is False
    assert row["reason"] == "HARDLINK_PRESENT"


def test_registered_worktree_cache_is_not_discovered(monkeypatch, tmp_path):
    now = datetime(2026, 11, 10, tzinfo=timezone.utc)
    worktree = tmp_path / "worktree"
    cache = worktree / "__pycache__"
    _old_tree(cache, now)
    (tmp_path / "proc").mkdir()

    plan = _plan(monkeypatch, tmp_path, now, registered={worktree})
    assert plan["candidates"] == []


def test_unavailable_worktree_registry_fails_closed(monkeypatch, tmp_path):
    now = datetime(2026, 11, 10, tzinfo=timezone.utc)
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
    now = datetime(2026, 11, 10, tzinfo=timezone.utc)
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
    now = datetime(2026, 11, 10, tzinfo=timezone.utc)
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
