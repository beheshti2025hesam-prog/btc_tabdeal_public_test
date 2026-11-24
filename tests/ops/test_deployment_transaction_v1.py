from __future__ import annotations
import hashlib
import json
from pathlib import Path
import pytest

from forward.deployment_transaction_v1 import (
    DeploymentTransactionError, POINTER_NAMES, snapshot_pointers,
    switch_release_pointers, rollback_release_pointers, restore_pointer_snapshot,
)

def _release(root: Path, release_id: str) -> Path:
    path = root / "releases" / release_id
    path.mkdir(parents=True)
    source = path / "app.py"
    source.write_text("print('immutable')\n", encoding="utf-8")
    manifest = {"commit_sha": release_id, "file_count": 1, "files": [
        {"path": "app.py", "sha256": hashlib.sha256(source.read_bytes()).hexdigest()}
    ]}
    raw = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()
    (path / "HES_RELEASE_MANIFEST_v1.json").write_bytes(raw)
    digest = hashlib.sha256(raw).hexdigest()
    (path / "HES_RELEASE_MANIFEST_v1.sha256").write_text(
        f"{digest}  HES_RELEASE_MANIFEST_v1.json\n", encoding="ascii"
    )
    return path

def _root(tmp_path):
    (tmp_path / "releases").mkdir()
    fallback = _release(tmp_path, "a" * 40)
    target = _release(tmp_path, "b" * 40)
    for name in POINTER_NAMES:
        (tmp_path / name).symlink_to(fallback)
    return fallback, target

def test_switch_and_rollback_all_pointers_to_verified_releases(tmp_path):
    fallback, target = _root(tmp_path)
    snapshot = switch_release_pointers(tmp_path, target.name)
    assert all((tmp_path / name).resolve() == target for name in POINTER_NAMES)
    rollback_release_pointers(tmp_path, fallback.name)
    assert all((tmp_path / name).resolve() == fallback for name in POINTER_NAMES)
    assert set(snapshot) == set(POINTER_NAMES)
    assert not list(tmp_path.glob(".*.tmp"))

def test_restore_snapshot_restores_each_original_pointer_target(tmp_path):
    fallback, target = _root(tmp_path)
    # Start with a deliberately mixed but valid pointer set.
    (tmp_path / "precision-current").unlink()
    (tmp_path / "precision-current").symlink_to(target)
    snapshot = snapshot_pointers(tmp_path)
    switch_release_pointers(tmp_path, target.name)
    restore_pointer_snapshot(tmp_path, snapshot)
    assert (tmp_path / "current").resolve() == fallback
    assert (tmp_path / "precision-current").resolve() == target
    assert (tmp_path / "dashboard-current").resolve() == fallback

def test_switch_refuses_invalid_release_before_changing_any_pointer(tmp_path):
    fallback, _ = _root(tmp_path)
    with pytest.raises(DeploymentTransactionError, match="RELEASE_PATH_INVALID"):
        switch_release_pointers(tmp_path, "missing")
    assert all((tmp_path / name).resolve() == fallback for name in POINTER_NAMES)

def test_snapshot_refuses_non_symlink_pointer(tmp_path):
    fallback, target = _root(tmp_path)
    (tmp_path / "dashboard-current").unlink()
    (tmp_path / "dashboard-current").write_text("not a symlink")
    with pytest.raises(DeploymentTransactionError, match="POINTER_NOT_SYMLINK"):
        switch_release_pointers(tmp_path, target.name)
    assert (tmp_path / "current").resolve() == fallback
