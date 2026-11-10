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
    return cleanup.build_cleanup_plan(
        now=now,
        registered_worktrees=registered if registered is not None else set(),
        worktree_registry_error=registry_error,
        proc_root=proc_root or tmp_path / "proc",
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
