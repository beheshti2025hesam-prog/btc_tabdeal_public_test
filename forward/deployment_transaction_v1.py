"""Atomic, fail-closed release-pointer transactions for HES."""
from __future__ import annotations

import os
from pathlib import Path
import uuid
from typing import Mapping

POINTER_NAMES = ("current", "precision-current", "dashboard-current")


class DeploymentTransactionError(RuntimeError):
    pass


def _release(root: Path, release_id: str) -> Path:
    root = Path(root).resolve(strict=True)
    releases = (root / "releases").resolve(strict=True)
    candidate = releases / release_id
    try:
        target = candidate.resolve(strict=True)
    except OSError as exc:
        raise DeploymentTransactionError("RELEASE_PATH_INVALID") from exc
    if target.parent != releases or target.name != release_id or not target.is_dir():
        raise DeploymentTransactionError("RELEASE_PATH_INVALID")
    from scripts.ops.build_release_manifest_v1 import verify_manifest
    try:
        verify_manifest(target)
    except Exception as exc:
        raise DeploymentTransactionError(f"RELEASE_MANIFEST_INVALID:{type(exc).__name__}") from exc
    return target


def snapshot_pointers(root: Path) -> dict[str, str]:
    root = Path(root).resolve(strict=True)
    releases = (root / "releases").resolve(strict=True)
    snapshot: dict[str, str] = {}
    for name in POINTER_NAMES:
        pointer = root / name
        if not pointer.is_symlink():
            raise DeploymentTransactionError(f"POINTER_NOT_SYMLINK:{name}")
        raw_target = os.readlink(pointer)
        target = (pointer.parent / raw_target).resolve(strict=True)
        if target.parent != releases or not target.is_dir():
            raise DeploymentTransactionError(f"POINTER_TARGET_INVALID:{name}")
        snapshot[name] = raw_target
    return snapshot


def _atomic_set(pointer: Path, target: Path) -> None:
    temp = pointer.with_name(f".{pointer.name}.{uuid.uuid4().hex}.tmp")
    try:
        os.symlink(str(target), temp)
        os.replace(temp, pointer)
        fd = os.open(pointer.parent, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    finally:
        try:
            temp.unlink()
        except FileNotFoundError:
            pass


def switch_release_pointers(root: Path, release_id: str) -> dict[str, str]:
    """Validate all pointers and target first, then atomically replace each pointer."""
    root = Path(root).resolve(strict=True)
    target = _release(root, release_id)
    snapshot = snapshot_pointers(root)
    changed: list[str] = []
    try:
        for name in POINTER_NAMES:
            _atomic_set(root / name, target)
            changed.append(name)
    except Exception:
        # Best-effort restoration to the exact pre-switch pointer set.
        for name in reversed(changed):
            old = (root / snapshot[name]).resolve(strict=True) if not Path(snapshot[name]).is_absolute() else Path(snapshot[name]).resolve(strict=True)
            _atomic_set(root / name, old)
        raise
    return snapshot


def rollback_release_pointers(root: Path, rollback_release_id: str) -> dict[str, str]:
    """Rollback all application pointers to one verified immutable fallback release."""
    return switch_release_pointers(root, rollback_release_id)


def restore_pointer_snapshot(root: Path, snapshot: Mapping[str, str]) -> None:
    root = Path(root).resolve(strict=True)
    releases = (root / "releases").resolve(strict=True)
    if set(snapshot) != set(POINTER_NAMES):
        raise DeploymentTransactionError("POINTER_SNAPSHOT_INCOMPLETE")
    targets: dict[str, Path] = {}
    for name, raw in snapshot.items():
        pointer = root / name
        target = Path(raw)
        if not target.is_absolute():
            target = (pointer.parent / target).resolve(strict=True)
        else:
            target = target.resolve(strict=True)
        if target.parent != releases or not target.is_dir():
            raise DeploymentTransactionError(f"SNAPSHOT_TARGET_INVALID:{name}")
        targets[name] = target
    for name in POINTER_NAMES:
        _atomic_set(root / name, targets[name])
