#!/usr/bin/env python3
"""Fail-closed planner and reversible quarantine for narrowly allowlisted temp caches.

Default mode is read-only. The only actionable objects are old __pycache__ and
.pytest_cache directories below /tmp or /var/tmp. No recursive deletion exists.
"""
from __future__ import annotations

import argparse
import ctypes
import errno
import fcntl
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
import uuid
from typing import Any

POLICY_VERSION = "hes_tmp_cache_quarantine_v1"
ALLOWED_ROOTS = (Path("/tmp"), Path("/var/tmp"))
ALLOWED_NAMES = {"__pycache__", ".pytest_cache"}
MIN_AGE_DAYS = 14
MAX_CANDIDATES = 10
MAX_CANDIDATE_BYTES = 128 * 1024 * 1024
MAX_BATCH_BYTES = 512 * 1024 * 1024
MAX_TREE_ENTRIES = 5_000
MAX_DISCOVERED_CANDIDATES = 100
QUARANTINE_NAME = ".hes-idlm-quarantine-v1"
AUDIT_PATH = Path("/var/lib/hes-idlm/cleanup-audit.jsonl")
REPO_ROOT = Path("/opt/hes-trade-agent")
CONFIRM_PHRASE = "QUARANTINE HES TEMP CACHES"


class CleanupSafetyError(RuntimeError):
    pass


def _sha256_file(path: Path, expected: os.stat_result) -> str:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags)
    digest = hashlib.sha256()
    try:
        before = os.fstat(fd)
        if (
            before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns
        ) != (
            expected.st_dev, expected.st_ino, expected.st_size, expected.st_mtime_ns, expected.st_ctime_ns
        ):
            raise CleanupSafetyError("FILE_CHANGED_DURING_OPEN")
        while True:
            chunk = os.read(fd, 1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
        after = os.fstat(fd)
        if (
            after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns
        ) != (
            before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns
        ):
            raise CleanupSafetyError("FILE_CHANGED_DURING_HASH")
    finally:
        os.close(fd)
    return digest.hexdigest()


def _tree_snapshot(path: Path) -> tuple[dict[str, Any], set[tuple[int, int]]]:
    root_st = path.lstat()
    if not stat.S_ISDIR(root_st.st_mode) or stat.S_ISLNK(root_st.st_mode):
        raise CleanupSafetyError("TARGET_NOT_REAL_DIRECTORY")
    device = root_st.st_dev
    stack = [path]
    rows: list[dict[str, Any]] = []
    identities: set[tuple[int, int]] = set()
    total_bytes = 0
    owner_ids: set[int] = set()
    group_ids: set[int] = set()

    while stack:
        current = stack.pop()
        current_st = current.lstat()
        if stat.S_ISLNK(current_st.st_mode) or current_st.st_dev != device:
            raise CleanupSafetyError("SYMLINK_OR_MOUNT_BOUNDARY")
        owner_ids.add(current_st.st_uid)
        group_ids.add(current_st.st_gid)
        identities.add((current_st.st_dev, current_st.st_ino))
        rel = "." if current == path else current.relative_to(path).as_posix()
        if current_st.st_mode & (stat.S_ISUID | stat.S_ISGID):
            raise CleanupSafetyError("SPECIAL_PERMISSION_BIT")
        rows.append({
            "path": rel, "kind": "directory", "dev": current_st.st_dev,
            "ino": current_st.st_ino, "mode": stat.S_IMODE(current_st.st_mode),
            "uid": current_st.st_uid, "gid": current_st.st_gid,
            "size": 0, "mtime_ns": current_st.st_mtime_ns,
            "ctime_ns": current_st.st_ctime_ns,
        })
        if len(rows) > MAX_TREE_ENTRIES:
            raise CleanupSafetyError("TREE_ENTRY_LIMIT")
        with os.scandir(current) as entries:
            children = sorted((Path(entry.path) for entry in entries), key=lambda p: p.name)
        current_after = current.lstat()
        if (
            current_after.st_dev, current_after.st_ino, current_after.st_mtime_ns,
            current_after.st_ctime_ns, current_after.st_size,
        ) != (
            current_st.st_dev, current_st.st_ino, current_st.st_mtime_ns,
            current_st.st_ctime_ns, current_st.st_size,
        ):
            raise CleanupSafetyError("DIRECTORY_CHANGED_DURING_SCAN")
        for child in reversed(children):
            st = child.lstat()
            if stat.S_ISLNK(st.st_mode):
                raise CleanupSafetyError("SYMLINK_PRESENT")
            if st.st_dev != device:
                raise CleanupSafetyError("MOUNT_BOUNDARY_PRESENT")
            if st.st_mode & (stat.S_ISUID | stat.S_ISGID):
                raise CleanupSafetyError("SPECIAL_PERMISSION_BIT")
            owner_ids.add(st.st_uid)
            group_ids.add(st.st_gid)
            identities.add((st.st_dev, st.st_ino))
            rel_child = child.relative_to(path).as_posix()
            if stat.S_ISDIR(st.st_mode):
                stack.append(child)
            elif stat.S_ISREG(st.st_mode):
                if st.st_nlink != 1:
                    raise CleanupSafetyError("HARDLINK_PRESENT")
                if st.st_size > MAX_CANDIDATE_BYTES:
                    raise CleanupSafetyError("FILE_SIZE_LIMIT")
                total_bytes += st.st_blocks * 512 if hasattr(st, "st_blocks") else st.st_size
                if total_bytes > MAX_CANDIDATE_BYTES:
                    raise CleanupSafetyError("CANDIDATE_SIZE_LIMIT")
                content_hash = _sha256_file(child, st)
                rows.append({
                    "path": rel_child, "kind": "file", "dev": st.st_dev,
                    "ino": st.st_ino, "mode": stat.S_IMODE(st.st_mode),
                    "uid": st.st_uid, "gid": st.st_gid, "size": st.st_size,
                    "mtime_ns": st.st_mtime_ns, "ctime_ns": st.st_ctime_ns,
                    "nlink": st.st_nlink, "sha256": content_hash,
                })
                if len(rows) > MAX_TREE_ENTRIES:
                    raise CleanupSafetyError("TREE_ENTRY_LIMIT")
            else:
                raise CleanupSafetyError("SPECIAL_FILE_PRESENT")

    if len(owner_ids) != 1 or len(group_ids) != 1:
        raise CleanupSafetyError("MIXED_OWNERSHIP")
    rows.sort(key=lambda row: row["path"])
    # Directory ctime changes on a legitimate rename; retain it in the scan
    # evidence but omit it from the stable tree fingerprint. File ctime stays
    # hashed so content/metadata mutation remains detectable.
    fingerprint_rows = []
    for row in rows:
        stable_row = dict(row)
        if stable_row["kind"] == "directory":
            stable_row.pop("ctime_ns", None)
        fingerprint_rows.append(stable_row)
    encoded = json.dumps(fingerprint_rows, sort_keys=True, separators=(",", ":")).encode()
    return {
        "tree_sha256": hashlib.sha256(encoded).hexdigest(),
        "allocated_bytes": total_bytes,
        "entry_count": len(rows),
        "device": device,
        "inode": root_st.st_ino,
        "mtime_ns": root_st.st_mtime_ns,
        "owner_uid": next(iter(owner_ids)),
        "owner_gid": next(iter(group_ids)),
        "entries": rows,
    }, identities


def _open_reference_scan(
    identities: set[tuple[int, int]], proc_root: Path = Path("/proc")
) -> tuple[list[dict[str, Any]], list[str]]:
    found: list[dict[str, Any]] = []
    errors: list[str] = []
    try:
        processes = list(proc_root.iterdir())
    except OSError as exc:
        return [], [f"PROC_ROOT:{type(exc).__name__}"]
    for process in processes:
        if not process.name.isdigit():
            continue
        pid = process.name
        for area in ("fd",):
            fd_dir = process / area
            try:
                fds = list(fd_dir.iterdir())
            except FileNotFoundError:
                continue
            except PermissionError:
                errors.append(f"PID_{pid}_FD_PERMISSION")
                continue
            except OSError as exc:
                if exc.errno not in (2, 3):
                    errors.append(f"PID_{pid}_FD_{type(exc).__name__}")
                continue
            for fd_path in fds:
                try:
                    st = fd_path.stat()
                except FileNotFoundError:
                    continue
                except PermissionError:
                    errors.append(f"PID_{pid}_FD_STAT_PERMISSION")
                    continue
                except OSError as exc:
                    if exc.errno not in (errno.ENOENT, errno.ESRCH):
                        errors.append(f"PID_{pid}_FD_STAT_{type(exc).__name__}")
                    continue
                if (st.st_dev, st.st_ino) in identities:
                    found.append({"pid": int(pid), "fd": fd_path.name})
        for ref_name in ("cwd", "root", "exe"):
            ref_path = process / ref_name
            try:
                ref_stat = ref_path.stat()
            except FileNotFoundError:
                continue
            except PermissionError:
                errors.append(f"PID_{pid}_{ref_name.upper()}_PERMISSION")
                continue
            except OSError as exc:
                if exc.errno not in (errno.ENOENT, errno.ESRCH):
                    errors.append(f"PID_{pid}_{ref_name.upper()}_{type(exc).__name__}")
                continue
            if (ref_stat.st_dev, ref_stat.st_ino) in identities:
                found.append({"pid": int(pid), "reference": ref_name})
        maps_path = process / "maps"
        try:
            lines = maps_path.read_text(encoding="utf-8", errors="replace").splitlines()
        except FileNotFoundError:
            continue
        except PermissionError:
            errors.append(f"PID_{pid}_MAPS_PERMISSION")
            continue
        except OSError as exc:
            if exc.errno not in (errno.ENOENT, errno.ESRCH):
                errors.append(f"PID_{pid}_MAPS_{type(exc).__name__}")
            continue
        for line in lines:
            fields = line.split()
            if len(fields) < 5:
                continue
            try:
                major_hex, minor_hex = fields[3].split(":")
                dev = os.makedev(int(major_hex, 16), int(minor_hex, 16))
                inode = int(fields[4])
            except (ValueError, OSError):
                continue
            if inode and (dev, inode) in identities:
                found.append({"pid": int(pid), "mapping": fields[5] if len(fields) > 5 else "anonymous"})
    return found, errors


def _inside(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _load_worktrees(repo_root: Path) -> tuple[set[Path], str | None]:
    try:
        import subprocess
        result = subprocess.run(
            ["git", "-C", str(repo_root), "worktree", "list", "--porcelain"],
            capture_output=True, text=True, timeout=10, check=True,
        )
        paths = {
            Path(os.path.abspath(line[len("worktree "):]))
            for line in result.stdout.splitlines() if line.startswith("worktree ")
        }
        return paths, None
    except Exception as exc:
        return set(), f"{type(exc).__name__}:{str(exc)[:100]}"


def _discover_targets(root: Path, registered: set[Path], device: int) -> tuple[list[Path], list[str]]:
    targets: list[Path] = []
    errors: list[str] = []
    stack = [root]
    quarantine = root / QUARANTINE_NAME
    while stack:
        current = stack.pop()
        try:
            with os.scandir(current) as entries:
                children = sorted((Path(entry.path) for entry in entries), key=lambda p: p.name)
        except OSError as exc:
            errors.append(f"{current}:{type(exc).__name__}")
            continue
        for child in reversed(children):
            if child == quarantine or child.name == QUARANTINE_NAME:
                continue
            try:
                st = child.lstat()
            except OSError as exc:
                errors.append(f"{child}:{type(exc).__name__}")
                continue
            if stat.S_ISLNK(st.st_mode) or st.st_dev != device:
                continue
            if not stat.S_ISDIR(st.st_mode):
                continue
            if any(_inside(child, wt) or _inside(wt, child) for wt in registered):
                continue
            if child.name in ALLOWED_NAMES:
                targets.append(child)
                if len(targets) > MAX_DISCOVERED_CANDIDATES:
                    errors.append("CANDIDATE_DISCOVERY_LIMIT")
                    return targets[:MAX_DISCOVERED_CANDIDATES], errors
                continue
            stack.append(child)
    return targets, errors


def build_cleanup_plan(
    *, now: datetime | None = None, registered_worktrees: set[Path] | None = None,
    worktree_registry_error: str | None = None, proc_root: Path = Path("/proc"),
) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    if registered_worktrees is None:
        registered_worktrees, worktree_registry_error = _load_worktrees(REPO_ROOT)
    candidates: list[dict[str, Any]] = []
    scan_errors: list[str] = []
    if worktree_registry_error:
        scan_errors.append("WORKTREE_REGISTRY_UNAVAILABLE")
    if not worktree_registry_error:
        for root in ALLOWED_ROOTS:
            try:
                root_st = root.lstat()
                if stat.S_ISLNK(root_st.st_mode) or not stat.S_ISDIR(root_st.st_mode):
                    raise CleanupSafetyError("ROOT_NOT_REAL_DIRECTORY")
                targets, errors = _discover_targets(root, registered_worktrees or set(), root_st.st_dev)
                scan_errors.extend(errors)
            except (OSError, CleanupSafetyError) as exc:
                scan_errors.append(f"{root}:{type(exc).__name__}")
                continue
            for target in targets:
                row: dict[str, Any] = {
                    "path": str(target), "eligible": False, "reason": "UNASSESSED",
                    "automatic_action": "NONE",
                }
                try:
                    snapshot, identities = _tree_snapshot(target)
                    age_seconds = now.timestamp() - snapshot["mtime_ns"] / 1_000_000_000
                    if age_seconds < MIN_AGE_DAYS * 86400:
                        raise CleanupSafetyError("YOUNGER_THAN_14_DAYS")
                    newest_change_ns = max(
                        max(entry["mtime_ns"], entry.get("ctime_ns", entry["mtime_ns"]))
                        for entry in snapshot["entries"]
                    )
                    if now.timestamp() * 1_000_000_000 - newest_change_ns < MIN_AGE_DAYS * 86400 * 1_000_000_000:
                        raise CleanupSafetyError("RECENT_ENTRY_PRESENT")
                    refs, ref_errors = _open_reference_scan(identities, proc_root=proc_root)
                    if ref_errors:
                        raise CleanupSafetyError("PROCESS_REFERENCE_SCAN_INCOMPLETE")
                    if refs:
                        raise CleanupSafetyError("OPEN_PROCESS_REFERENCE")
                    row.update(snapshot)
                    row.update({
                        "eligible": True, "reason": "ALLOWLISTED_OLD_CACHE_NO_REFERENCES",
                        "process_references": [], "automatic_action": "NONE",
                    })
                except (OSError, CleanupSafetyError) as exc:
                    row["reason"] = str(exc)[:160] or type(exc).__name__
                candidates.append(row)

    eligible = [row for row in candidates if row["eligible"]]
    eligible.sort(key=lambda row: row["path"])
    batch: list[dict[str, Any]] = []
    batch_bytes = 0
    for row in eligible:
        size = int(row["allocated_bytes"])
        if len(batch) >= MAX_CANDIDATES or batch_bytes + size > MAX_BATCH_BYTES:
            row["eligible"] = False
            row["reason"] = "BATCH_BUDGET_EXCEEDED"
            continue
        batch.append(row)
        batch_bytes += size
    manifest = {
        "schema": "hes_idlm_cache_cleanup_plan_v1",
        "policy_version": POLICY_VERSION,
        "generated_at": now.isoformat(),
        "minimum_age_days": MIN_AGE_DAYS,
        "allowed_roots": [str(root) for root in ALLOWED_ROOTS],
        "allowed_directory_names": sorted(ALLOWED_NAMES),
        "max_candidates": MAX_CANDIDATES,
        "max_candidate_bytes": MAX_CANDIDATE_BYTES,
        "max_batch_bytes": MAX_BATCH_BYTES,
        "worktree_registry": {
            "repo_root": str(REPO_ROOT), "registered_count": len(registered_worktrees or set()),
            "error": worktree_registry_error,
        },
        "scan_errors": scan_errors,
        "candidates": candidates,
        "eligible_count": len(batch),
        "eligible_allocated_bytes": batch_bytes,
        "execution_enabled": False,
        "deletion_authorized": False,
        "automatic_action": "NONE",
    }
    return manifest


def _reject_symlink_components(path: Path) -> None:
    absolute = path.absolute()
    cursor = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        cursor = cursor / part
        try:
            st = cursor.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(st.st_mode):
            raise CleanupSafetyError("SYMLINK_PATH_COMPONENT")


def _append_audit(event: dict[str, Any], audit_path: Path = AUDIT_PATH) -> None:
    if os.geteuid() != 0:
        raise CleanupSafetyError("AUDIT_REQUIRES_ROOT")
    _reject_symlink_components(audit_path.parent)
    audit_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    parent_fd = _open_directory_chain(audit_path.parent)
    try:
        parent_st = os.fstat(parent_fd)
        if not stat.S_ISDIR(parent_st.st_mode) or parent_st.st_uid != 0:
            raise CleanupSafetyError("AUDIT_PARENT_UNTRUSTED")
        os.fchmod(parent_fd, 0o700)
        flags = os.O_WRONLY | os.O_APPEND | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
        fd = os.open(audit_path.name, flags, 0o600, dir_fd=parent_fd)
        try:
            st = os.fstat(fd)
            if (
                not stat.S_ISREG(st.st_mode) or st.st_uid != 0 or st.st_nlink != 1
                or st.st_size > 64 * 1024 * 1024
            ):
                raise CleanupSafetyError("AUDIT_FILE_UNTRUSTED_OR_SIZE_LIMIT")
            os.fchmod(fd, 0o600)
            fcntl.flock(fd, fcntl.LOCK_EX)
            payload = (json.dumps(event, sort_keys=True) + "\n").encode()
            if st.st_size + len(payload) > 64 * 1024 * 1024:
                raise CleanupSafetyError("AUDIT_SIZE_LIMIT")
            view = memoryview(payload)
            while view:
                written = os.write(fd, view)
                view = view[written:]
            os.fsync(fd)
        finally:
            os.close(fd)
        os.fsync(parent_fd)
    finally:
        os.close(parent_fd)


def _read_regular_file(
    path: Path, *, max_bytes: int = 64 * 1024 * 1024,
    require_root_owner: bool = False, dir_fd: int | None = None,
) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path.name, flags, dir_fd=dir_fd) if dir_fd is not None else os.open(path, flags)
    chunks: list[bytes] = []
    total = 0
    try:
        before = os.fstat(fd)
        if (
            not stat.S_ISREG(before.st_mode) or before.st_nlink != 1
            or before.st_size > max_bytes or stat.S_IMODE(before.st_mode) & 0o022
            or (require_root_owner and (before.st_uid != 0 or stat.S_IMODE(before.st_mode) & 0o077))
        ):
            raise CleanupSafetyError("REGULAR_FILE_UNSAFE")
        while True:
            chunk = os.read(fd, 1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > max_bytes:
                raise CleanupSafetyError("REGULAR_FILE_SIZE_LIMIT")
            chunks.append(chunk)
        after = os.fstat(fd)
        if (
            before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns,
            before.st_ctime_ns, before.st_mode, before.st_uid, before.st_gid, before.st_nlink,
        ) != (
            after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns,
            after.st_ctime_ns, after.st_mode, after.st_uid, after.st_gid, after.st_nlink,
        ) or total != before.st_size:
            raise CleanupSafetyError("REGULAR_FILE_CHANGED_DURING_READ")
    finally:
        os.close(fd)
    return b"".join(chunks)


def _manifest_digest(path: Path) -> str:
    return hashlib.sha256(_read_regular_file(path)).hexdigest()


def _open_directory_chain(path: Path) -> int:
    absolute = path.absolute()
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    fd = os.open(absolute.anchor, flags)
    try:
        for part in absolute.parts[1:]:
            next_fd = os.open(part, flags, dir_fd=fd)
            os.close(fd)
            fd = next_fd
        if not stat.S_ISDIR(os.fstat(fd).st_mode):
            raise CleanupSafetyError("PATH_COMPONENT_NOT_DIRECTORY")
        return fd
    except Exception:
        os.close(fd)
        raise


def _rename_noreplace(
    source_name: str, destination_name: str, *, source_dir_fd: int, destination_dir_fd: int
) -> None:
    renameat2 = getattr(ctypes.CDLL(None, use_errno=True), "renameat2", None)
    if renameat2 is None:
        raise CleanupSafetyError("ATOMIC_NOREPLACE_RENAME_UNAVAILABLE")
    renameat2.argtypes = [
        ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint,
    ]
    renameat2.restype = ctypes.c_int
    result = renameat2(
        source_dir_fd, os.fsencode(source_name),
        destination_dir_fd, os.fsencode(destination_name), 1,
    )
    if result != 0:
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error), destination_name)


def _write_new_manifest(path: Path, rendered: str) -> str:
    absolute = path.absolute()
    parent_fd = _open_directory_chain(absolute.parent)
    try:
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
        fd = os.open(absolute.name, flags, 0o600, dir_fd=parent_fd)
        try:
            st = os.fstat(fd)
            if not stat.S_ISREG(st.st_mode) or st.st_nlink != 1:
                raise CleanupSafetyError("MANIFEST_OUTPUT_UNSAFE")
            os.fchmod(fd, 0o600)
            payload = rendered.encode("utf-8")
            view = memoryview(payload)
            while view:
                written = os.write(fd, view)
                view = view[written:]
            os.fsync(fd)
        finally:
            os.close(fd)
        os.fsync(parent_fd)
        return hashlib.sha256(payload).hexdigest()
    finally:
        os.close(parent_fd)


def quarantine_manifest(
    manifest_path: Path, *, expected_sha256: str, confirmation: str,
    audit_path: Path = AUDIT_PATH, proc_root: Path = Path("/proc"),
) -> list[dict[str, Any]]:
    if os.geteuid() != 0:
        raise CleanupSafetyError("APPLY_REQUIRES_ROOT")
    if confirmation != CONFIRM_PHRASE:
        raise CleanupSafetyError("EXPLICIT_CONFIRMATION_REQUIRED")
    absolute_manifest = manifest_path.absolute()
    manifest_parent_fd = _open_directory_chain(absolute_manifest.parent)
    try:
        manifest_bytes = _read_regular_file(
            absolute_manifest, require_root_owner=True, dir_fd=manifest_parent_fd
        )
    finally:
        os.close(manifest_parent_fd)
    if hashlib.sha256(manifest_bytes).hexdigest() != expected_sha256:
        raise CleanupSafetyError("MANIFEST_DIGEST_MISMATCH")
    manifest = json.loads(manifest_bytes.decode("utf-8"))
    if manifest.get("policy_version") != POLICY_VERSION or manifest.get("schema") != "hes_idlm_cache_cleanup_plan_v1":
        raise CleanupSafetyError("POLICY_OR_SCHEMA_MISMATCH")
    if manifest.get("allowed_roots") != [str(root) for root in ALLOWED_ROOTS]:
        raise CleanupSafetyError("ROOT_SCOPE_MISMATCH")
    if manifest.get("allowed_directory_names") != sorted(ALLOWED_NAMES):
        raise CleanupSafetyError("CACHE_NAME_SCOPE_MISMATCH")
    if manifest.get("minimum_age_days") != MIN_AGE_DAYS:
        raise CleanupSafetyError("AGE_POLICY_MISMATCH")
    if (
        manifest.get("execution_enabled") is not False
        or manifest.get("deletion_authorized") is not False
        or manifest.get("automatic_action") != "NONE"
    ):
        raise CleanupSafetyError("PLAN_EXECUTION_FLAGS_UNSAFE")
    if manifest.get("scan_errors") or manifest.get("worktree_registry", {}).get("error"):
        raise CleanupSafetyError("PLAN_HAS_SCAN_ERRORS")
    eligible_items = [item for item in manifest.get("candidates", []) if item.get("eligible")]
    if len(eligible_items) != manifest.get("eligible_count") or len(eligible_items) > MAX_CANDIDATES:
        raise CleanupSafetyError("CANDIDATE_COUNT_MISMATCH")
    total_planned_bytes = 0
    seen_paths: set[str] = set()
    for item in eligible_items:
        if not isinstance(item.get("path"), str) or item.get("path") in seen_paths:
            raise CleanupSafetyError("DUPLICATE_OR_INVALID_CANDIDATE_PATH")
        if item.get("automatic_action") != "NONE":
            raise CleanupSafetyError("CANDIDATE_ACTION_FLAG_UNSAFE")
        seen_paths.add(item.get("path"))
        size = int(item.get("allocated_bytes", -1))
        if size < 0 or size > MAX_CANDIDATE_BYTES:
            raise CleanupSafetyError("CANDIDATE_SIZE_POLICY_MISMATCH")
        total_planned_bytes += size
    if total_planned_bytes > MAX_BATCH_BYTES or total_planned_bytes != manifest.get("eligible_allocated_bytes"):
        raise CleanupSafetyError("BATCH_SIZE_POLICY_MISMATCH")
    actions: list[dict[str, Any]] = []
    for item in eligible_items:
        if not item.get("eligible"):
            continue
        source = Path(item["path"])
        root = next((r for r in ALLOWED_ROOTS if _inside(source, r)), None)
        if root is None or source.name not in ALLOWED_NAMES:
            raise CleanupSafetyError("PATH_OUTSIDE_ALLOWLIST")
        fresh = build_cleanup_plan(
            registered_worktrees=None, proc_root=proc_root
        )
        match = next((r for r in fresh["candidates"] if r["path"] == str(source)), None)
        if not match or not match.get("eligible") or match.get("tree_sha256") != item.get("tree_sha256"):
            raise CleanupSafetyError("STALE_OR_CHANGED_MANIFEST")
        root_st = root.lstat()
        quarantine_root = root / QUARANTINE_NAME
        if quarantine_root.exists() and (quarantine_root.is_symlink() or not quarantine_root.is_dir()):
            raise CleanupSafetyError("QUARANTINE_ROOT_UNSAFE")
        quarantine_root.mkdir(mode=0o700, exist_ok=True)
        quarantine_st = quarantine_root.lstat()
        if (
            stat.S_ISLNK(quarantine_st.st_mode)
            or not stat.S_ISDIR(quarantine_st.st_mode)
            or quarantine_st.st_uid != 0
            or stat.S_IMODE(quarantine_st.st_mode) != 0o700
        ):
            raise CleanupSafetyError("QUARANTINE_ROOT_UNTRUSTED")
        if quarantine_st.st_dev != root_st.st_dev:
            raise CleanupSafetyError("QUARANTINE_DEVICE_MISMATCH")
        run_dir = quarantine_root / uuid.uuid4().hex
        run_dir.mkdir(mode=0o700, exist_ok=False)
        os.chmod(run_dir, 0o700)
        run_dir_st = run_dir.lstat()
        if not stat.S_ISDIR(run_dir_st.st_mode) or run_dir_st.st_uid != 0 or stat.S_IMODE(run_dir_st.st_mode) != 0o700:
            raise CleanupSafetyError("QUARANTINE_RUN_DIRECTORY_UNTRUSTED")
        for directory in (root, quarantine_root):
            fd = os.open(directory, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
        destination = run_dir / f"{source.name}-{uuid.uuid4().hex}"
        event = {
            "at": datetime.now(timezone.utc).isoformat(), "policy_version": POLICY_VERSION,
            "action": "QUARANTINE_INTENT", "source": str(source),
            "destination": str(destination), "tree_sha256": item["tree_sha256"],
            "device": item["device"], "inode": item["inode"],
            "manifest_sha256": expected_sha256,
        }
        _append_audit(event, audit_path)
        # Pin both parent directories with no-follow directory descriptors.
        source_parent_fd = _open_directory_chain(source.parent)
        run_dir_fd = _open_directory_chain(run_dir)
        try:
            # Revalidate immediately before the atomic same-filesystem rename.
            try:
                current_snapshot, identities = _tree_snapshot(source)
                refs, errors = _open_reference_scan(identities, proc_root=proc_root)
                source_st = os.stat(source.name, dir_fd=source_parent_fd, follow_symlinks=False)
                if (
                    errors or refs
                    or current_snapshot["tree_sha256"] != item["tree_sha256"]
                    or not stat.S_ISDIR(source_st.st_mode)
                    or (source_st.st_dev, source_st.st_ino) != (item["device"], item["inode"])
                ):
                    raise CleanupSafetyError("PRE_RENAME_REVALIDATION_FAILED")
                try:
                    os.stat(destination.name, dir_fd=run_dir_fd, follow_symlinks=False)
                except FileNotFoundError:
                    pass
                else:
                    raise CleanupSafetyError("QUARANTINE_DESTINATION_EXISTS")
            except Exception as exc:
                _append_audit({
                    **event, "at": datetime.now(timezone.utc).isoformat(),
                    "action": "QUARANTINE_ABORTED", "reason": f"{type(exc).__name__}:{str(exc)[:120]}",
                }, audit_path)
                raise
            try:
                _rename_noreplace(
                    source.name, destination.name,
                    source_dir_fd=source_parent_fd, destination_dir_fd=run_dir_fd,
                )
            except OSError as exc:
                _append_audit({
                    **event, "at": datetime.now(timezone.utc).isoformat(),
                    "action": "QUARANTINE_ABORTED", "reason": f"RENAME_FAILED:{type(exc).__name__}",
                }, audit_path)
                raise
            moved_st = os.stat(destination.name, dir_fd=run_dir_fd, follow_symlinks=False)
            if not stat.S_ISDIR(moved_st.st_mode) or (
                moved_st.st_dev, moved_st.st_ino
            ) != (item["device"], item["inode"]):
                _append_audit({
                    **event, "at": datetime.now(timezone.utc).isoformat(),
                    "action": "QUARANTINE_IDENTITY_MISMATCH",
                }, audit_path)
                raise CleanupSafetyError("POST_RENAME_IDENTITY_MISMATCH")
            post_snapshot, post_identities = _tree_snapshot(destination)
            post_refs, post_errors = _open_reference_scan(post_identities, proc_root=proc_root)
            if post_snapshot["tree_sha256"] != item["tree_sha256"]:
                _append_audit({
                    **event, "at": datetime.now(timezone.utc).isoformat(),
                    "action": "QUARANTINE_IDENTITY_MISMATCH",
                }, audit_path)
                raise CleanupSafetyError("POST_RENAME_CONTENT_MISMATCH")
            if post_errors or post_refs:
                _append_audit({
                    **event, "at": datetime.now(timezone.utc).isoformat(),
                    "action": "QUARANTINE_HELD",
                    "reason": "POST_RENAME_REFERENCE_SCAN_INCOMPLETE_OR_BUSY",
                }, audit_path)
                raise CleanupSafetyError("POST_RENAME_REFERENCES_PRESENT_OR_UNVERIFIED")
            os.fsync(source_parent_fd)
            os.fsync(run_dir_fd)
        finally:
            os.close(source_parent_fd)
            os.close(run_dir_fd)
        done = {**event, "at": datetime.now(timezone.utc).isoformat(), "action": "QUARANTINED"}
        _append_audit(done, audit_path)
        actions.append(done)
    return actions


def _restore_identity_scan(path: Path) -> set[tuple[int, int]]:
    root_st = path.lstat()
    if not stat.S_ISDIR(root_st.st_mode) or stat.S_ISLNK(root_st.st_mode):
        raise CleanupSafetyError("RESTORE_ROOT_NOT_DIRECTORY")
    identities: set[tuple[int, int]] = set()
    stack = [path]
    while stack:
        current = stack.pop()
        current_st = current.lstat()
        identities.add((current_st.st_dev, current_st.st_ino))
        if len(identities) > MAX_TREE_ENTRIES:
            raise CleanupSafetyError("RESTORE_IDENTITY_SCAN_LIMIT")
        if not stat.S_ISDIR(current_st.st_mode) or stat.S_ISLNK(current_st.st_mode):
            continue
        with os.scandir(current) as entries:
            children = [Path(entry.path) for entry in entries]
        for child in children:
            child_st = child.lstat()
            identities.add((child_st.st_dev, child_st.st_ino))
            if len(identities) > MAX_TREE_ENTRIES:
                raise CleanupSafetyError("RESTORE_IDENTITY_SCAN_LIMIT")
            if stat.S_ISDIR(child_st.st_mode) and not stat.S_ISLNK(child_st.st_mode):
                if child_st.st_dev == root_st.st_dev:
                    stack.append(child)
    return identities


def restore_quarantine(
    quarantine_path: Path, *, confirmation: str, audit_path: Path = AUDIT_PATH
) -> dict[str, Any]:
    if os.geteuid() != 0:
        raise CleanupSafetyError("RESTORE_REQUIRES_ROOT")
    if confirmation != "RESTORE HES QUARANTINED CACHE":
        raise CleanupSafetyError("RESTORE_CONFIRMATION_REQUIRED")
    _reject_symlink_components(quarantine_path)
    if quarantine_path.is_symlink() or not quarantine_path.is_dir():
        raise CleanupSafetyError("QUARANTINE_PATH_INVALID")
    if quarantine_path.parent.parent.name != QUARANTINE_NAME:
        raise CleanupSafetyError("NOT_IDLM_QUARANTINE")
    quarantine_root_st = quarantine_path.parent.parent.lstat()
    run_dir_st = quarantine_path.parent.lstat()
    if (
        stat.S_ISLNK(quarantine_root_st.st_mode) or not stat.S_ISDIR(quarantine_root_st.st_mode)
        or quarantine_root_st.st_uid != 0 or stat.S_IMODE(quarantine_root_st.st_mode) != 0o700
        or stat.S_ISLNK(run_dir_st.st_mode) or not stat.S_ISDIR(run_dir_st.st_mode)
        or run_dir_st.st_uid != 0 or stat.S_IMODE(run_dir_st.st_mode) != 0o700
    ):
        raise CleanupSafetyError("QUARANTINE_DIRECTORY_UNTRUSTED")
    audit_parent_fd = _open_directory_chain(audit_path.parent)
    try:
        try:
            audit_bytes = _read_regular_file(
                audit_path, require_root_owner=True, dir_fd=audit_parent_fd
            )
            lines = audit_bytes.decode("utf-8").splitlines()
        except (OSError, UnicodeDecodeError, CleanupSafetyError) as exc:
            raise CleanupSafetyError("AUDIT_UNAVAILABLE_OR_UNSAFE") from exc
    finally:
        os.close(audit_parent_fd)
    matched_event = None
    for line in reversed(lines):
        try:
            event = json.loads(line)
        except json.JSONDecodeError as exc:
            raise CleanupSafetyError("AUDIT_CORRUPT") from exc
        if (
            event.get("destination") == str(quarantine_path)
            and event.get("action") in {
                "QUARANTINED", "QUARANTINE_INTENT",
                "QUARANTINE_ABORTED", "QUARANTINE_IDENTITY_MISMATCH", "QUARANTINE_HELD",
            }
        ):
            matched_event = event
            break
    if matched_event is None or matched_event.get("action") in {
        "QUARANTINE_ABORTED", "QUARANTINE_IDENTITY_MISMATCH",
    }:
        raise CleanupSafetyError("RESTORE_ORIGIN_NOT_AUDITED")
    original = Path(matched_event["source"])
    if original.exists() or original.is_symlink():
        raise CleanupSafetyError("RESTORE_DESTINATION_EXISTS")
    root = next((r for r in ALLOWED_ROOTS if _inside(original, r)), None)
    if root is None or original.name not in ALLOWED_NAMES:
        raise CleanupSafetyError("RESTORE_ORIGIN_OUTSIDE_ALLOWLIST")
    _reject_symlink_components(original.parent)
    if original.parent.stat().st_dev != quarantine_path.stat().st_dev:
        raise CleanupSafetyError("RESTORE_DEVICE_MISMATCH")
    restore_fallback = False
    try:
        restored_snapshot, identities = _tree_snapshot(quarantine_path)
        restore_device, restore_inode = restored_snapshot["device"], restored_snapshot["inode"]
        if (
            restored_snapshot["tree_sha256"] != matched_event.get("tree_sha256")
            or (restore_device, restore_inode)
            != (matched_event.get("device"), matched_event.get("inode"))
        ):
            raise CleanupSafetyError("QUARANTINE_CONTENT_OR_IDENTITY_CHANGED")
    except (OSError, CleanupSafetyError):
        root_st = quarantine_path.lstat()
        restore_device, restore_inode = root_st.st_dev, root_st.st_ino
        if (restore_device, restore_inode) != (
            matched_event.get("device"), matched_event.get("inode")
        ):
            raise CleanupSafetyError("QUARANTINE_ROOT_IDENTITY_CHANGED")
        identities = _restore_identity_scan(quarantine_path)
        restore_fallback = True
    refs, ref_errors = _open_reference_scan(identities)
    if ref_errors or refs:
        raise CleanupSafetyError("QUARANTINE_STILL_REFERENCED")
    _append_audit({
        "at": datetime.now(timezone.utc).isoformat(), "policy_version": POLICY_VERSION,
        "action": "RESTORE_INTENT", "source": str(quarantine_path), "destination": str(original),
        "tree_sha256": matched_event.get("tree_sha256"),
        "fallback_tree_unverified": restore_fallback,
    }, audit_path)
    quarantine_parent_fd = _open_directory_chain(quarantine_path.parent)
    original_parent_fd = _open_directory_chain(original.parent)
    try:
        source_st = os.stat(quarantine_path.name, dir_fd=quarantine_parent_fd, follow_symlinks=False)
        if not stat.S_ISDIR(source_st.st_mode) or (
            source_st.st_dev, source_st.st_ino
        ) != (restore_device, restore_inode):
            raise CleanupSafetyError("RESTORE_SOURCE_IDENTITY_MISMATCH")
        try:
            os.stat(original.name, dir_fd=original_parent_fd, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            raise CleanupSafetyError("RESTORE_DESTINATION_EXISTS")
        _rename_noreplace(
            quarantine_path.name, original.name,
            source_dir_fd=quarantine_parent_fd, destination_dir_fd=original_parent_fd,
        )
        os.fsync(quarantine_parent_fd)
        os.fsync(original_parent_fd)
    finally:
        os.close(quarantine_parent_fd)
        os.close(original_parent_fd)
    _append_audit({
        "at": datetime.now(timezone.utc).isoformat(), "policy_version": POLICY_VERSION,
        "action": "RESTORED", "source": str(quarantine_path), "destination": str(original),
    }, audit_path)
    return {"action": "RESTORED", "path": str(original)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="Write a dry-run JSON manifest.")
    parser.add_argument("--apply-manifest", type=Path, help="Quarantine only after digest and phrase confirmation.")
    parser.add_argument("--confirm-manifest-sha256")
    parser.add_argument("--confirm", default="")
    parser.add_argument("--restore-quarantine", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.restore_quarantine:
            result = restore_quarantine(args.restore_quarantine, confirmation=args.confirm)
            print(json.dumps(result, sort_keys=True))
            return 0
        if args.apply_manifest:
            actions = quarantine_manifest(
                args.apply_manifest, expected_sha256=args.confirm_manifest_sha256 or "",
                confirmation=args.confirm,
            )
            print(json.dumps({"actions": actions}, sort_keys=True))
            return 0
        plan = build_cleanup_plan()
        rendered = json.dumps(plan, indent=2, sort_keys=True) + "\n"
        if args.output:
            digest = _write_new_manifest(args.output, rendered)
            print(f"DRY_RUN_WRITTEN sha256={digest} path={args.output} eligible={plan['eligible_count']} action=NONE")
        else:
            sys.stdout.write(rendered)
        return 0
    except (CleanupSafetyError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"FAIL_CLOSED:{type(exc).__name__}:{str(exc)}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
