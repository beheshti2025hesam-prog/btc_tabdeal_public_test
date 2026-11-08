#!/usr/bin/env python3
"""Read-only HES storage inventory and retention-candidate audit.

This tool deliberately has no delete, move, truncate, compression, or rotation
operation. Unknown data is KEEP. It emits a manifest for human review only.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
from typing import Any

DEFAULT_ROOTS = (
    "/tmp",
    "/var/tmp",
    "/var/backups/hes-trade-agent",
    "/var/backups/hes-trade-agent/encrypted-local",
    "/opt/hes-trade-agent",
    "/opt/sentinelx-cloud-core",
    "/home/hes-remote",
    "/var/log",
    "/var/cache",
    "/var/lib",
)
BACKUP_PARENT = Path("/var/backups/hes-trade-agent")
BACKUP_RE = re.compile(r"^hes-full-(\d{8}T\d{6}Z)\.tar\.gz\.gpg$")
CACHE_NAMES = {
    ".cache", ".npm", ".pytest_cache", ".mypy_cache", ".ruff_cache",
    "__pycache__", "node_modules", "hes-playwright-browsers",
}
PROTECTED_NAMES = {
    "data", "evidence", "archive", "releases", "candidates", ".worktrees",
    ".isolated-main-20261105", ".isolated-pr448-20261105",
}


def _allocated_size(st: os.stat_result) -> int:
    blocks = getattr(st, "st_blocks", None)
    return int(blocks * 512) if blocks is not None else int(st.st_size)


def _tree_usage(path: Path, device: int) -> tuple[int, int, int]:
    """Return allocated bytes, regular-file count, and error count; never follow symlinks."""
    try:
        root_st = path.lstat()
    except OSError:
        return 0, 0, 1
    if stat.S_ISLNK(root_st.st_mode):
        return 0, 0, 0
    if not stat.S_ISDIR(root_st.st_mode):
        return _allocated_size(root_st), int(stat.S_ISREG(root_st.st_mode)), 0
    total = 0
    files = 0
    errors = 0
    stack = [path]
    while stack:
        current = stack.pop()
        try:
            with os.scandir(current) as entries:
                for entry in entries:
                    try:
                        st = entry.stat(follow_symlinks=False)
                        if st.st_dev != device:
                            continue
                        if stat.S_ISLNK(st.st_mode):
                            continue
                        if stat.S_ISDIR(st.st_mode):
                            stack.append(Path(entry.path))
                        elif stat.S_ISREG(st.st_mode):
                            total += _allocated_size(st)
                            files += 1
                    except OSError:
                        errors += 1
        except OSError:
            errors += 1
    return total, files, errors


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _classify(
    path: Path, *, age_days: float, is_symlink: bool, stale_after_days: int = 7,
    registered_worktrees: set[Path] | None = None, worktree_registry_ok: bool = True,
) -> tuple[str, str]:
    if is_symlink:
        return "KEEP_SYMLINK", "Symlink target is not followed; review its owner and target explicitly."
    if registered_worktrees and any(
        path == worktree or _is_relative_to(path, worktree)
        for worktree in registered_worktrees
    ):
        return "KEEP_REGISTERED_WORKTREE", "Git currently registers this path as a worktree; preserve it until explicitly retired and unregistered."
    if _is_relative_to(path, BACKUP_PARENT):
        return "KEEP_BACKUP", "Backup data remains protected until offsite coverage and restore are verified."
    if path.name in PROTECTED_NAMES or path.name.startswith("current"):
        return "KEEP_PROTECTED", "Canonical data, evidence, release, rollback, or worktree material is protected."
    if path.name in CACHE_NAMES or path.parent == Path("/var/cache"):
        return "REVIEW_REGENERABLE_CACHE", "Potentially regenerable cache; no deletion permission is implied."
    if path == Path("/var/log/journal"):
        return "REVIEW_SYSTEM_LOG_RETENTION", "System journal retention must be tuned through journald policy, not ad-hoc deletion."
    if path in {Path("/tmp"), Path("/var/tmp")} or path.parent in {Path("/tmp"), Path("/var/tmp")}:
        if not worktree_registry_ok:
            return "KEEP_UNKNOWN", "Git worktree registry could not be verified; preserve temporary paths until dependencies are known."
        if age_days >= stale_after_days:
            return "REVIEW_STALE_TEMP", "Older temporary workspace; verify run/evidence ownership and process references."
        return "REVIEW_TEMP", "Temporary workspace; verify ownership and reproducibility before any action."
    if path.name in {"logs", "log"}:
        return "REVIEW_LOG_POLICY", "Check writer, rotation, and retention policy before changing log data."
    return "KEEP_UNKNOWN", "Unknown classification or dependency; fail closed and keep."


def _backup_groups(records: list[dict[str, Any]]) -> dict[str, int]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in records:
        if row.get("kind") != "file":
            continue
        match = BACKUP_RE.match(Path(row["path"]).name)
        if match:
            day = match.group(1)[:8]
            grouped.setdefault(day, []).append(row)
    extra_snapshots = 0
    for rows in grouped.values():
        rows.sort(key=lambda row: Path(row["path"]).name)
        if len(rows) <= 1:
            continue
        for row in rows[:-1]:
            row["classification"] = "REVIEW_SAME_DAY_EXTRA_BACKUP"
            row["reason"] = (
                "Additional full backup snapshot from a day with multiple snapshots. It is not proven "
                "content-identical; keep until restore/offsite proof and a versioned retention policy authorize pruning."
            )
            extra_snapshots += 1
        rows[-1]["classification"] = "KEEP_LATEST_SAME_DAY_BACKUP"
    return {
        "backup_days": len(grouped),
        "backup_archives": sum(map(len, grouped.values())),
        "same_day_extra_snapshot_candidates": extra_snapshots,
    }


def _load_registered_worktrees(repo_root: Path) -> tuple[set[Path], str | None]:
    if not repo_root.is_dir():
        return set(), "repository_root_missing"
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_root), "worktree", "list", "--porcelain"],
            capture_output=True, text=True, timeout=10, check=True,
        )
    except Exception as exc:
        return set(), f"{type(exc).__name__}:{str(exc)[:120]}"
    paths: set[Path] = set()
    for line in result.stdout.splitlines():
        if line.startswith("worktree "):
            paths.add(Path(os.path.abspath(line[len("worktree "):])))
    return paths, None


def build_report(
    scan_roots: list[Path], *, now: datetime | None = None, stale_after_days: int = 7,
    registered_worktrees: set[Path] | None = None,
    worktree_repo_root: Path = Path("/opt/hes-trade-agent"),
) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    if registered_worktrees is None:
        registered_worktrees, worktree_registry_error = _load_registered_worktrees(worktree_repo_root)
    else:
        worktree_registry_error = None
    records: list[dict[str, Any]] = []
    seen: set[str] = set()
    for root in scan_roots:
        try:
            root_st = root.lstat()
        except OSError as exc:
            records.append({
                "path": str(root), "kind": "missing_or_unreadable",
                "classification": "KEEP_UNKNOWN", "reason": type(exc).__name__,
                "automatic_action": "NONE",
            })
            continue
        if stat.S_ISLNK(root_st.st_mode):
            records.append({
                "path": str(root), "kind": "symlink", "classification": "KEEP_SYMLINK",
                "reason": "Scan root is a symlink; not followed.", "automatic_action": "NONE",
            })
            continue
        if not stat.S_ISDIR(root_st.st_mode):
            children = [root]
            device = root_st.st_dev
        else:
            device = root_st.st_dev
            try:
                children = [Path(entry.path) for entry in os.scandir(root)]
            except OSError as exc:
                records.append({
                    "path": str(root), "kind": "unreadable", "classification": "KEEP_UNKNOWN",
                    "reason": type(exc).__name__, "automatic_action": "NONE",
                })
                continue
        for path in children:
            key = str(path)
            if key in seen:
                continue
            seen.add(key)
            try:
                st = path.lstat()
                is_link = stat.S_ISLNK(st.st_mode)
                age_days = max(0.0, (now.timestamp() - st.st_mtime) / 86400.0)
                if is_link:
                    size, files, errors, kind = 0, 0, 0, "symlink"
                elif stat.S_ISDIR(st.st_mode):
                    size, files, errors = _tree_usage(path, device)
                    kind = "directory"
                else:
                    size, files, errors = _allocated_size(st), int(stat.S_ISREG(st.st_mode)), 0
                    kind = "file"
                classification, reason = _classify(
                    path, age_days=age_days, is_symlink=is_link,
                    stale_after_days=stale_after_days,
                    registered_worktrees=registered_worktrees,
                    worktree_registry_ok=worktree_registry_error is None,
                )
                records.append({
                    "path": key, "kind": kind, "allocated_bytes": size, "file_count": files,
                    "scan_errors": errors,
                    "mtime_utc": datetime.fromtimestamp(st.st_mtime, timezone.utc).isoformat(),
                    "age_days": round(age_days, 2), "classification": classification,
                    "reason": reason, "automatic_action": "NONE",
                })
            except OSError as exc:
                records.append({
                    "path": key, "kind": "unreadable", "classification": "KEEP_UNKNOWN",
                    "reason": type(exc).__name__, "automatic_action": "NONE",
                })

    backup_summary = _backup_groups(records)
    records.sort(key=lambda row: (-int(row.get("allocated_bytes", 0)), row["path"]))
    try:
        usage = shutil.disk_usage("/")
        vfs = os.statvfs("/")
        disk = {
            "total_bytes": usage.total,
            "used_bytes": usage.used,
            "free_bytes": usage.free,
            "free_percent": round(100.0 * usage.free / usage.total, 2) if usage.total else None,
            "inode_total": vfs.f_files,
            "inode_free_for_user": vfs.f_favail,
            "inode_free_percent": round(100.0 * vfs.f_favail / vfs.f_files, 2) if vfs.f_files else None,
        }
    except OSError as exc:
        disk = {"error": type(exc).__name__}
    return {
        "schema": "hes_data_lifecycle_audit_v1",
        "generated_at": now.isoformat(),
        "mode": "READ_ONLY_DRY_RUN",
        "automatic_action": "NONE",
        "stale_temp_review_threshold_days": stale_after_days,
        "disk": disk,
        "backup_summary": backup_summary,
        "worktree_registry": {
            "repo_root": str(worktree_repo_root),
            "registered_count": len(registered_worktrees),
            "paths": sorted(str(path) for path in registered_worktrees),
            "error": worktree_registry_error,
        },
        "protected_data_rules": [
            "Trade and NO_TRADE journals/outcomes; decision evidence and counterfactuals.",
            "Canonical candles and raw event payloads with source/session/timestamps/hash/registry lineage.",
            "Model, policy, config, run hashes, provenance, audit/security, backup and rollback data.",
            "Unknown or dependency-unverified items are KEEP.",
            "Opaque sequence-like fields are not generic event IDs, ordering guarantees, or deletion keys.",
        ],
        "items": records,
        "limitations": [
            "Directory sizes are allocated-byte estimates and may omit mountpoints, unreadable entries, and open-but-unlinked files.",
            "This report does not prove a path is unused; process, descriptor, service, job, Git, and recovery dependencies require separate checks.",
            "No record in this report authorizes deletion, compression, movement, rotation, or pruning.",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scan-root", action="append", default=None, help="Root to inventory; may be repeated.")
    parser.add_argument("--stale-after-days", type=int, default=7)
    parser.add_argument(
        "--output", type=Path,
        help="Optional JSON output path; choose a location outside scanned roots.",
    )
    args = parser.parse_args(argv)
    roots = [Path(path) for path in (args.scan_root or DEFAULT_ROOTS)]
    report = build_report(roots, stale_after_days=args.stale_after_days)
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
        print(f"REPORT_WRITTEN path={args.output} items={len(report['items'])} mode={report['mode']}")
    else:
        sys.stdout.write(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
