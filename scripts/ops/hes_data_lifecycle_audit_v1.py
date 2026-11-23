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

# HES roots are scanned before platform roots so shared inodes are attributed to HES.
DEFAULT_ROOTS = (
    "/opt/hes-trade-agent",
    "/srv/hes-evidence",
    "/var/backups/hes-trade-agent",
    "/tmp",
    "/var/tmp",
    "/var/lib",
    "/var/log",
    "/var/cache",
    "/var/backups/hes-trade-agent/encrypted-local",
    "/var/backups/hes-trade-agent/dropbox-staging",
    "/opt/sentinelx-cloud-core",
    "/home/hes-remote",
)
TEMP_ROOTS = {Path("/tmp"), Path("/var/tmp")}
RUNTIME_ROOTS = {Path("/var/lib"), Path("/var/log"), Path("/var/cache")}
PLATFORM_TEMP_EXACT = {".X11-unix", ".ICE-unix", ".XIM-unix", ".font-unix"}
PLATFORM_TEMP_PREFIXES = ("systemd-private-", "snap-private-tmp", "apt-", "apt.")
HES_TEMP_PREFIXES = ("hes-", "hes_", "hes.", "p398", "phead", "t398", "h398", "pytest-of")
EVIDENCE_ROOT = Path("/srv/hes-evidence")
BACKUP_PARENT = Path("/var/backups/hes-trade-agent")
BACKUP_STAGING = BACKUP_PARENT / "dropbox-staging"
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


def _tree_usage(
    path: Path, device: int, seen_inodes: set[tuple[int, int]]
) -> tuple[int, int, int, int, int, int]:
    """Return logical bytes, globally unique physical bytes, shared-inode bytes, files, dirs, errors.

    Directory metadata is included. Symlinks are never followed or counted as target data.
    The shared inode set is global to the exact IDLM scan, including overlapping roots.
    """
    try:
        root_st = path.lstat()
    except OSError:
        return 0, 0, 0, 0, 0, 1
    if root_st.st_dev != device or stat.S_ISLNK(root_st.st_mode):
        return 0, 0, 0, 0, 0, 0

    logical = 0
    unique = 0
    shared = 0
    files = 0
    directories = 0
    errors = 0

    def account(st: os.stat_result) -> None:
        nonlocal logical, unique, shared
        size = _allocated_size(st)
        logical += size
        key = (int(st.st_dev), int(st.st_ino))
        if key in seen_inodes:
            shared += size
        else:
            unique += size
            seen_inodes.add(key)

    account(root_st)
    if not stat.S_ISDIR(root_st.st_mode):
        return logical, unique, shared, int(stat.S_ISREG(root_st.st_mode)), 0, errors

    directories += 1
    stack = [path]
    while stack:
        current = stack.pop()
        try:
            with os.scandir(current) as entries:
                for entry in entries:
                    try:
                        st = entry.stat(follow_symlinks=False)
                        if st.st_dev != device or stat.S_ISLNK(st.st_mode):
                            continue
                        account(st)
                        if stat.S_ISDIR(st.st_mode):
                            directories += 1
                            stack.append(Path(entry.path))
                        elif stat.S_ISREG(st.st_mode):
                            files += 1
                    except OSError:
                        errors += 1
        except OSError:
            errors += 1
    return logical, unique, shared, files, directories, errors

def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False



def _ownership_scope(
    path: Path, *, owner_uid: int, project_owner_uid: int,
    registered_worktrees: set[Path] | None = None,
) -> str:
    """Classify the storage owner without guessing from file content."""
    if _is_relative_to(path, Path("/opt/hes-trade-agent")):
        return "HES_PROJECT"
    if _is_relative_to(path, EVIDENCE_ROOT):
        return "HES_EVIDENCE"
    if _is_relative_to(path, BACKUP_PARENT):
        return "HES_BACKUP"
    if path.parent in TEMP_ROOTS:
        name = path.name.lower()
        if name in PLATFORM_TEMP_EXACT or name.startswith(PLATFORM_TEMP_PREFIXES):
            return "PLATFORM_TEMP"
        if registered_worktrees and path in registered_worktrees:
            return "HES_TEMP"
        # Root-owned and project-service-owned temp files are conservatively included.
        if name.startswith(HES_TEMP_PREFIXES) or owner_uid in {0, project_owner_uid}:
            return "HES_TEMP"
        return "UNCLASSIFIED_TEMP"
    if path.parent in RUNTIME_ROOTS and path.name.lower() in {"hes", "hes-trade-agent"}:
        return "HES_RUNTIME"
    if path.parent in RUNTIME_ROOTS and path.name.lower().startswith(("hes-", "hes_", "hes.")):
        return "HES_RUNTIME"
    if _is_relative_to(path, Path("/opt/sentinelx-cloud-core")) or _is_relative_to(path, Path("/home/hes-remote")):
        return "PLATFORM"
    return "OTHER"

def _classify(
    path: Path, *, age_days: float, is_symlink: bool, stale_after_days: int = 7,
    registered_worktrees: set[Path] | None = None, worktree_registry_ok: bool = True,
) -> tuple[str, str]:
    if is_symlink:
        return "KEEP_SYMLINK", "Symlink target is not followed; review its owner and target explicitly."
    if registered_worktrees and path in registered_worktrees:
        return "KEEP_REGISTERED_WORKTREE", "Git currently registers this path as a worktree; preserve it until explicitly retired and unregistered."
    if _is_relative_to(path, EVIDENCE_ROOT):
        return "KEEP_EVIDENCE", "Immutable project evidence store; preserve for provenance, audit, and recovery."
    if _is_relative_to(path, BACKUP_STAGING):
        return "KEEP_BACKUP_STAGING", "Encrypted staging artifact is protected until key, manifest, and remote upload are verified; local staging is not an offsite copy."
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
        # An unregistered Git clone/worktree can contain dirty, unpushed, or ignored user data.
        # Keep it until its exact commit, status, ignored files, and remote provenance are reviewed.
        if path.is_dir() and os.path.lexists(path / ".git"):
            return "KEEP_UNREGISTERED_GIT_WORKSPACE", "Temporary path contains its own Git metadata; preserve until dirty/untracked/ignored state and remote commit provenance are verified."
        archive_suffixes = (".tar", ".tar.gz", ".tar.zst", ".tar.zst.gpg", ".tar.gz.gpg", ".gpg", ".zip", ".bundle", ".7z", ".zst")
        evidence_tokens = (
            "backup", "restore", "recovery", "archive", "evidence", "journal", "model",
            "dataset", "candidate", "release", "rollback", "snapshot", "fulltest",
            "soak", "smoke", "hash-check", "security", "review", "audit", "training",
            "lineage", "lab", "differential", "preview", "restic", "strace",
        )
        name = path.name.lower()
        if name.endswith(archive_suffixes) or any(token in name for token in evidence_tokens):
            return "KEEP_TEMP_EVIDENCE", "Temporary path looks like an archive, backup, recovery, test, model, dataset, review, or audit artifact; preserve until exact content and retention evidence authorize compaction."
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



def _backup_retention_plan(records: list[dict[str, Any]], now: datetime) -> dict[str, Any]:
    counts: dict[str, int] = {}
    for row in records:
        if row.get("kind") != "file":
            continue
        name = Path(row["path"]).name
        if name.endswith(".tar.gz.gpg.sha256"):
            continue
        if not name.endswith(".tar.gz.gpg"):
            continue
        match = BACKUP_RE.match(name)
        if not match:
            retention_class = "KEEP_UNPARSED_BACKUP_NAME"
            reason = "Encrypted-backup filename is not understood; keep until manually identified."
        else:
            try:
                stamp = datetime.strptime(match.group(1), "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
            except ValueError:
                stamp = None
            if stamp is None:
                retention_class = "KEEP_UNPARSED_BACKUP_NAME"
                reason = "Encrypted-backup timestamp is invalid; keep until manually identified."
            else:
                age_days = (now.date() - stamp.date()).days
                if age_days < 0:
                    retention_class = "KEEP_FUTURE_DATED_BACKUP"
                    reason = "Future-dated backup; fail closed and preserve archive and sidecar."
                elif age_days < 7:
                    retention_class = "KEEP_DAILY_WINDOW"
                    reason = "Within the current seven-day daily retention window."
                elif age_days < 28 and stamp.weekday() == 6:
                    retention_class = "KEEP_WEEKLY_ANCHOR"
                    reason = "Sunday snapshot within the current 28-day weekly retention window."
                elif age_days < 180 and stamp.day == 1:
                    retention_class = "KEEP_MONTHLY_ANCHOR"
                    reason = "First-of-month snapshot within the current 180-day monthly retention window."
                else:
                    retention_class = "REVIEW_RETENTION_EXPIRED"
                    reason = "Outside current daily/weekly/monthly windows; review only, never auto-delete from this report."
        row["retention_class"] = retention_class
        row["retention_reason"] = reason
        row["retention_action"] = "NONE"
        row["checksum_sidecar_present"] = Path(row["path"] + ".sha256").is_file()
        counts[retention_class] = counts.get(retention_class, 0) + 1
    return {
        "policy_version": "existing_local_backup_retention_v1",
        "daily_window_days": 7,
        "weekly_window_days": 28,
        "monthly_window_days": 180,
        "retention_class_counts": counts,
        "expired_review_candidates": counts.get("REVIEW_RETENTION_EXPIRED", 0),
        "future_dated_kept": counts.get("KEEP_FUTURE_DATED_BACKUP", 0),
        "unparsed_kept": counts.get("KEEP_UNPARSED_BACKUP_NAME", 0),
        "restore_status": "NOT_CHECKED_BY_SCANNER",
        "offsite_status": "NOT_CHECKED_BY_SCANNER",
        "deletion_authorized": False,
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
    try:
        project_owner_uid = worktree_repo_root.stat().st_uid
    except OSError:
        project_owner_uid = os.getuid()

    records: list[dict[str, Any]] = []
    seen_paths: set[str] = set()
    seen_inodes: set[tuple[int, int]] = set()
    missing_roots: list[str] = []

    for root in scan_roots:
        try:
            root_st = root.lstat()
        except OSError as exc:
            missing_roots.append(str(root))
            records.append({
                "path": str(root), "kind": "missing_or_unreadable",
                "allocated_bytes": 0, "logical_allocated_bytes": 0,
                "unique_allocated_bytes": 0, "shared_inode_path_bytes": 0,
                "file_count": 0, "directory_count": 0, "scan_errors": 1,
                "ownership_scope": _ownership_scope(
                    root, owner_uid=-1, project_owner_uid=project_owner_uid,
                    registered_worktrees=registered_worktrees,
                ),
                "classification": "KEEP_UNKNOWN", "reason": type(exc).__name__,
                "automatic_action": "NONE",
            })
            continue
        if stat.S_ISLNK(root_st.st_mode):
            missing_roots.append(str(root))
            records.append({
                "path": str(root), "kind": "symlink", "allocated_bytes": 0,
                "logical_allocated_bytes": 0, "unique_allocated_bytes": 0,
                "shared_inode_path_bytes": 0, "file_count": 0, "directory_count": 0,
                "scan_errors": 1,
                "ownership_scope": _ownership_scope(
                    root, owner_uid=root_st.st_uid, project_owner_uid=project_owner_uid,
                    registered_worktrees=registered_worktrees,
                ),
                "classification": "KEEP_SYMLINK",
                "reason": "Scan root is a symlink; not followed and its scope is incomplete.",
                "automatic_action": "NONE",
            })
            continue

        device = root_st.st_dev
        if stat.S_ISDIR(root_st.st_mode):
            try:
                children = [Path(entry.path) for entry in os.scandir(root)]
            except OSError as exc:
                missing_roots.append(str(root))
                records.append({
                    "path": str(root), "kind": "unreadable", "allocated_bytes": 0,
                    "logical_allocated_bytes": 0, "unique_allocated_bytes": 0,
                    "shared_inode_path_bytes": 0, "file_count": 0, "directory_count": 0,
                    "scan_errors": 1,
                    "ownership_scope": _ownership_scope(
                        root, owner_uid=root_st.st_uid, project_owner_uid=project_owner_uid,
                        registered_worktrees=registered_worktrees,
                    ),
                    "classification": "KEEP_UNKNOWN", "reason": type(exc).__name__,
                    "automatic_action": "NONE",
                })
                continue
        else:
            children = [root]

        def scope_priority(candidate: Path) -> tuple[int, str]:
            try:
                owner_uid = candidate.lstat().st_uid
            except OSError:
                owner_uid = -1
            scope = _ownership_scope(
                candidate, owner_uid=owner_uid, project_owner_uid=project_owner_uid,
                registered_worktrees=registered_worktrees,
            )
            if scope.startswith("HES_"):
                priority = 0
            elif scope == "UNCLASSIFIED_TEMP":
                priority = 1
            else:
                priority = 2
            return priority, str(candidate)

        children.sort(key=scope_priority)
        for path in children:
            key = str(path)
            if key in seen_paths:
                continue
            seen_paths.add(key)
            try:
                st = path.lstat()
                is_link = stat.S_ISLNK(st.st_mode)
                age_days = max(0.0, (now.timestamp() - st.st_mtime) / 86400.0)
                scope = _ownership_scope(
                    path, owner_uid=st.st_uid, project_owner_uid=project_owner_uid,
                    registered_worktrees=registered_worktrees,
                )
                if is_link:
                    logical = unique = shared = files = directories = errors = 0
                    kind = "symlink"
                else:
                    logical, unique, shared, files, directories, errors = _tree_usage(
                        path, device, seen_inodes
                    )
                    kind = "directory" if stat.S_ISDIR(st.st_mode) else "file"

                classification, reason = _classify(
                    path, age_days=age_days, is_symlink=is_link,
                    stale_after_days=stale_after_days,
                    registered_worktrees=registered_worktrees,
                    worktree_registry_ok=worktree_registry_error is None,
                )
                if scope == "PLATFORM_TEMP":
                    classification = "KEEP_PLATFORM_TEMP"
                    reason = "Platform-private temporary path; excluded from HES application storage."
                elif scope == "UNCLASSIFIED_TEMP":
                    classification = "KEEP_UNKNOWN"
                    reason = "Temporary path owner is not mapped to HES or platform; included conservatively and blocks budget acceptance."
                elif scope == "HES_RUNTIME":
                    classification = "KEEP_HES_RUNTIME"
                    reason = "HES runtime state/log data; preserve and include in the local HES storage budget."

                records.append({
                    "path": key,
                    "kind": kind,
                    # Backward-compatible allocated_bytes remains the logical path sum.
                    "allocated_bytes": logical,
                    "logical_allocated_bytes": logical,
                    "unique_allocated_bytes": unique,
                    "shared_inode_path_bytes": shared,
                    "file_count": files,
                    "directory_count": directories,
                    "scan_errors": errors,
                    "ownership_scope": scope,
                    "mtime_utc": datetime.fromtimestamp(st.st_mtime, timezone.utc).isoformat(),
                    "age_days": round(age_days, 2),
                    "classification": classification,
                    "reason": reason,
                    "automatic_action": "NONE",
                })
            except OSError as exc:
                records.append({
                    "path": key, "kind": "unreadable", "allocated_bytes": 0,
                    "logical_allocated_bytes": 0, "unique_allocated_bytes": 0,
                    "shared_inode_path_bytes": 0, "file_count": 0, "directory_count": 0,
                    "scan_errors": 1,
                    "ownership_scope": _ownership_scope(
                        path, owner_uid=-1, project_owner_uid=project_owner_uid,
                        registered_worktrees=registered_worktrees,
                    ),
                    "classification": "KEEP_UNKNOWN", "reason": type(exc).__name__,
                    "automatic_action": "NONE",
                })

    backup_summary = _backup_groups(records)
    backup_retention_plan = _backup_retention_plan(records, now)
    records.sort(key=lambda row: (-int(row.get("allocated_bytes", 0)), row["path"]))
    unclassified_temp = [row for row in records if row.get("ownership_scope") == "UNCLASSIFIED_TEMP"]
    scan_summary = {
        "item_count": len(records),
        "scan_errors": sum(int(row.get("scan_errors", 0)) for row in records),
        "logical_allocated_bytes": sum(int(row.get("logical_allocated_bytes", 0)) for row in records),
        "unique_allocated_bytes": sum(int(row.get("unique_allocated_bytes", 0)) for row in records),
        "shared_inode_path_bytes": sum(int(row.get("shared_inode_path_bytes", 0)) for row in records),
        "unclassified_temp_items": len(unclassified_temp),
        "unclassified_temp_bytes": sum(int(row.get("unique_allocated_bytes", 0)) for row in unclassified_temp),
        "hes_temp_items": sum(row.get("ownership_scope") == "HES_TEMP" for row in records),
        "hes_temp_unique_allocated_bytes": sum(int(row.get("unique_allocated_bytes", 0)) for row in records if row.get("ownership_scope") == "HES_TEMP"),
        "hes_runtime_items": sum(row.get("ownership_scope") == "HES_RUNTIME" for row in records),
        "hes_runtime_unique_allocated_bytes": sum(int(row.get("unique_allocated_bytes", 0)) for row in records if row.get("ownership_scope") == "HES_RUNTIME"),
        "missing_roots": missing_roots,
        "global_inode_dedup": True,
        "counting_method": "st_blocks*512; each (st_dev, st_ino) counted once globally across the exact IDLM scan roots; HES scopes are visited before platform scopes; symlinks are not followed",
    }
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
        "scan_summary": scan_summary,
        "backup_summary": backup_summary,
        "backup_retention_plan": backup_retention_plan,
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
            "Allocated bytes are reported both as logical path sums and globally unique physical inode allocation; unreadable entries and open-but-unlinked files remain outside the scan.",
            "The report does not prove a path is unused; process, descriptor, service, job, Git, and recovery dependencies require separate checks.",
            "Unknown temporary owners are included as unclassified bytes and block budget acceptance.",
            "No record in this report authorizes deletion, compression, movement, rotation, or pruning.",
        ],
    }

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scan-root", action="append", default=None, help="Root to inventory; may be repeated.")
    parser.add_argument("--stale-after-days", type=int, default=7)
    parser.add_argument(
        "--output", type=Path,
        help="Optional JSON output path; choose a location outside the scanned roots.",
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
