#!/usr/bin/env python3
"""Dependency-aware, fail-closed Smart Cleanup Manager (audit/planner only).

Consumes the existing IDLM v1 inventory. It has no delete, move, truncate,
compression, rotation, or service-mutation path. Unknown means KEEP.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import tempfile
from typing import Any

PROJECT_ROOT = Path("/opt/hes-trade-agent")
ACTIVE_POINTERS = (PROJECT_ROOT / "current", PROJECT_ROOT / "current-before-4329a3df")
PROTECTED_PREFIXES = ("KEEP_",)


def _under(path: str, root: str) -> bool:
    try:
        return os.path.commonpath((os.path.abspath(path), os.path.abspath(root))) == os.path.abspath(root)
    except (ValueError, OSError):
        return False


def _proc_references() -> tuple[list[dict[str, Any]], int]:
    """Collect live process cwd/root/fd paths without following candidate symlinks."""
    refs: list[dict[str, Any]] = []
    errors = 0
    proc = Path("/proc")
    try:
        pids = [p for p in proc.iterdir() if p.name.isdigit()]
    except OSError:
        return refs, 1
    for entry in pids:
        pid = entry.name
        try:
            comm = (entry / "comm").read_text(encoding="utf-8", errors="replace").strip()[:120]
        except OSError:
            comm = "unknown"
        for kind in ("cwd", "root"):
            try:
                target = os.readlink(entry / kind)
                if target.startswith("/"):
                    refs.append({"pid": int(pid), "comm": comm, "kind": kind, "path": target.removesuffix(" (deleted)")})
            except FileNotFoundError:
                pass
            except PermissionError:
                errors += 1
            except OSError:
                pass
        fd_dir = entry / "fd"
        try:
            fds = list(fd_dir.iterdir())
        except FileNotFoundError:
            continue
        except PermissionError:
            errors += 1
            continue
        except OSError:
            continue
        for fd in fds:
            try:
                target = os.readlink(fd)
                if target.startswith("/"):
                    refs.append({"pid": int(pid), "comm": comm, "kind": "fd", "path": target.removesuffix(" (deleted)")})
            except FileNotFoundError:
                pass
            except PermissionError:
                errors += 1
            except OSError:
                pass
    return refs, errors


def _expand_systemd_path_reference(unit: str, key: str, value: str) -> list[dict[str, str]]:
    refs: list[dict[str, str]] = []
    if value.strip():
        refs.append({"unit": unit, "property": key, "value": value[:2000]})
    bases = {
        "StateDirectory": "/var/lib",
        "CacheDirectory": "/var/cache",
        "LogsDirectory": "/var/log",
        "RuntimeDirectory": "/run",
    }
    base = bases.get(key)
    if base:
        for raw_name in value.split():
            name = raw_name.split(":", 1)[0]
            if not name:
                continue
            resolved = name if name.startswith("/") else str(Path(base) / name)
            refs.append({"unit": unit, "property": key + "_resolved", "value": resolved})
    return refs


def _is_concrete_systemd_unit(unit: str) -> bool:
    return not unit.endswith(("@.service", "@.timer"))


def _systemd_references() -> tuple[list[dict[str, str]], int]:
    """Inspect running units and enabled service/timer declarations for path dependencies."""
    refs: list[dict[str, str]] = []
    errors = 0
    unit_names: set[str] = set()
    listing_commands = (
        ["systemctl", "list-units", "--type=service", "--state=running", "--no-legend", "--plain"],
        ["systemctl", "list-units", "--type=timer", "--state=active", "--no-legend", "--plain"],
        ["systemctl", "list-unit-files", "--type=service", "--state=enabled", "--no-legend", "--no-pager"],
        ["systemctl", "list-unit-files", "--type=timer", "--state=enabled", "--no-legend", "--no-pager"],
    )
    for command in listing_commands:
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=20, check=False)
        except (OSError, subprocess.TimeoutExpired):
            errors += 1
            continue
        if result.returncode != 0:
            errors += 1
            continue
        for line in result.stdout.splitlines():
            fields = line.split()
            if fields and fields[0].endswith((".service", ".timer")) and _is_concrete_systemd_unit(fields[0]):
                unit_names.add(fields[0])
    properties = "ExecStart,WorkingDirectory,ReadWritePaths,ReadOnlyPaths,StateDirectory,CacheDirectory,LogsDirectory,RuntimeDirectory"
    for unit in sorted(unit_names):
        try:
            result = subprocess.run(
                ["systemctl", "show", unit, f"--property={properties}"],
                capture_output=True, text=True, timeout=10, check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            errors += 1
            continue
        if result.returncode != 0:
            errors += 1
            continue
        for prop in result.stdout.splitlines():
            key, _, value = prop.partition("=")
            refs.extend(_expand_systemd_path_reference(unit, key, value))
    return refs, errors


def _active_targets() -> tuple[list[str], list[str]]:
    targets: list[str] = []
    errors: list[str] = []
    for pointer in ACTIVE_POINTERS:
        try:
            if pointer.is_symlink():
                targets.append(str(pointer.resolve(strict=True)))
            else:
                errors.append(f"pointer_missing_or_not_symlink:{pointer}")
        except OSError as exc:
            errors.append(f"pointer_unresolved:{pointer}:{type(exc).__name__}")
    return targets, errors


def _matches_process(path: str, refs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    matches = []
    for ref in refs:
        target = ref.get("path", "")
        if target and (_under(target, path) or os.path.abspath(target) == os.path.abspath(path)):
            matches.append(ref)
    return matches[:50]


def _matches_unit(path: str, refs: list[dict[str, str]]) -> list[dict[str, str]]:
    matches = []
    for ref in refs:
        value = ref.get("value", "")
        if path in value:
            matches.append(ref)
    return matches[:30]


def _backup_status() -> dict[str, Any]:
    local_dir = Path("/var/backups/hes-trade-agent/encrypted-local")
    offsite_dir = Path("/var/backups/hes-trade-agent/offsite-staging")
    result: dict[str, Any] = {
        "local_latest": None,
        "local_latest_sidecar_verified": False,
        "offsite_latest": None,
        "offsite_latest_sidecar_verified": False,
        "dropbox_quota": None,
        "dropbox_remote_latest": None,
        "remote_hash_check": "NOT_RUN",
        "full_restore_status": "NOT_PROVEN",
        "selective_restore_status": "PREVIOUSLY_REPORTED_PASS_NOT_REPEATED_BY_THIS_RUN",
    }
    local = sorted(local_dir.glob("hes-full-*.tar.gz.gpg"), key=lambda p: p.name, reverse=True)
    if local:
        archive = local[0]
        sidecar = Path(str(archive) + ".sha256")
        result["local_latest"] = {"path": str(archive), "size_bytes": archive.stat().st_size, "sidecar_present": sidecar.is_file()}
        if sidecar.is_file():
            check = subprocess.run(["sha256sum", "-c", str(sidecar)], cwd=archive.parent, capture_output=True, text=True, timeout=180, check=False)
            result["local_latest_sidecar_verified"] = check.returncode == 0
            result["local_latest_sha256_check"] = check.stdout.strip()[-300:] if check.returncode == 0 else check.stderr.strip()[-300:]
    offsite = sorted(offsite_dir.glob("hes-offsite-core-*.tar.gz.gpg"), key=lambda p: p.name, reverse=True)
    if offsite:
        archive = offsite[0]
        sidecar = Path(str(archive) + ".sha256")
        result["offsite_latest"] = {"path": str(archive), "size_bytes": archive.stat().st_size, "sidecar_present": sidecar.is_file()}
        if sidecar.is_file():
            check = subprocess.run(["sha256sum", "-c", str(sidecar)], cwd=archive.parent, capture_output=True, text=True, timeout=60, check=False)
            result["offsite_latest_sidecar_verified"] = check.returncode == 0
    try:
        quota = subprocess.run(["rclone", "about", "hesdropbox:", "--json"], capture_output=True, text=True, timeout=45, check=False)
        if quota.returncode == 0:
            q = json.loads(quota.stdout)
            total, used, free = (int(q.get(k, 0)) for k in ("total", "used", "free"))
            result["dropbox_quota"] = {"total_bytes": total, "used_bytes": used, "free_bytes": free,
                                        "used_percent": round(100 * used / total, 2) if total else None}
        remote = subprocess.run(["rclone", "lsjson", "hesdropbox:HES Trade Agent Backups/hes-offsite-latest.tar.gz.gpg", "--stat"],
                                capture_output=True, text=True, timeout=45, check=False)
        if remote.returncode == 0:
            data = json.loads(remote.stdout)
            result["dropbox_remote_latest"] = {"size_bytes": int(data.get("Size", 0)), "modified": data.get("ModTime")}
            if offsite:
                with tempfile.TemporaryDirectory(prefix="hes-smart-cleanup-verify-", dir=str(offsite_dir)) as temp_dir:
                    local_link = Path(temp_dir) / "hes-offsite-latest.tar.gz.gpg"
                    os.link(offsite[0], local_link)
                    check = subprocess.run(
                        ["rclone", "check", temp_dir, "hesdropbox:HES Trade Agent Backups", "--one-way", "--checkers", "1"],
                        capture_output=True, text=True, timeout=240, check=False,
                    )
                    result["remote_hash_check"] = "PASS" if check.returncode == 0 else "FAIL"
                    result["remote_hash_check_detail"] = (check.stdout + check.stderr).strip()[-500:]
    except (OSError, subprocess.TimeoutExpired, ValueError, TypeError):
        result["dropbox_status"] = "UNAVAILABLE_OR_UNPARSEABLE"
    return result


def build_manager_report(audit: dict[str, Any], *, now: datetime | None = None,
                         proc_refs: list[dict[str, Any]] | None = None,
                         proc_errors: int | None = None,
                         unit_refs: list[dict[str, str]] | None = None,
                         unit_errors: int | None = None,
                         backup_status: dict[str, Any] | None = None,
                         active_targets: list[str] | None = None,
                         pointer_errors: list[str] | None = None) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    if proc_refs is None or proc_errors is None:
        proc_refs, proc_errors = _proc_references()
    if unit_refs is None or unit_errors is None:
        unit_refs, unit_errors = _systemd_references()
    if active_targets is None or pointer_errors is None:
        discovered_targets, discovered_errors = _active_targets()
        if active_targets is None:
            active_targets = discovered_targets
        if pointer_errors is None:
            pointer_errors = discovered_errors
    items = []
    for row in audit.get("items", []):
        path = str(row.get("path", ""))
        classification = str(row.get("classification", "KEEP_UNKNOWN"))
        process_matches = _matches_process(path, proc_refs)
        unit_matches = _matches_unit(path, unit_refs)
        active_match = any(_under(target, path) or _under(path, target) for target in active_targets)
        worktrees = audit.get("worktree_registry", {}).get("paths", [])
        worktree_match = any(_under(path, root) or _under(root, path) for root in worktrees)
        dependency_errors = int(proc_errors or 0) + int(unit_errors or 0) + len(pointer_errors)
        if process_matches or unit_matches or active_match or worktree_match:
            dependency_status = "BLOCKED_REFERENCED"
        elif dependency_errors:
            dependency_status = "UNKNOWN_FAIL_CLOSED"
        else:
            dependency_status = "NO_LIVE_REFERENCE_OBSERVED"
        protected = classification.startswith(PROTECTED_PREFIXES) or classification == "KEEP_UNKNOWN"
        if protected or dependency_status != "NO_LIVE_REFERENCE_OBSERVED":
            decision = "KEEP"
        else:
            decision = "REVIEW_ONLY"
        items.append({
            "path": path,
            "classification": classification,
            "allocated_bytes": int(row.get("allocated_bytes", 0)),
            "age_days": row.get("age_days"),
            "dependency_status": dependency_status,
            "process_references": process_matches,
            "systemd_references": unit_matches,
            "active_or_rollback_release_related": active_match,
            "registered_worktree_related": worktree_match,
            "decision": decision,
            "automatic_action": "NONE",
            "reason": "No destructive action exists in this manager; a clean dependency scan is not deletion authorization.",
        })
    disk = audit.get("disk", {})
    free_pct = disk.get("free_percent")
    if free_pct is None:
        pressure = "UNKNOWN"
    elif free_pct < 10:
        pressure = "CRITICAL"
    elif free_pct < 15:
        pressure = "WARN"
    else:
        pressure = "OK"
    backups = backup_status if backup_status is not None else _backup_status()
    remote_size_matches = bool(backups.get("offsite_latest") and backups.get("dropbox_remote_latest")
                               and int(backups["offsite_latest"].get("size_bytes", -1)) == int(backups["dropbox_remote_latest"].get("size_bytes", -2)))
    backup_gate = bool(backups.get("local_latest_sidecar_verified") and backups.get("offsite_latest_sidecar_verified")
                       and backups.get("remote_hash_check") == "PASS" and remote_size_matches
                       and backups.get("dropbox_quota"))
    return {
        "schema": "hes_smart_cleanup_manager_v1",
        "generated_at": now.isoformat(),
        "mode": "READ_ONLY_DEPENDENCY_AWARE_DRY_RUN",
        "source_audit_schema": audit.get("schema"),
        "source_audit_generated_at": audit.get("generated_at"),
        "inventory_items": len(items),
        "dependency_scan": {
            "process_reference_count": len(proc_refs), "process_scan_errors": proc_errors,
            "running_unit_reference_count": len(unit_refs), "unit_scan_errors": unit_errors,
            "active_release_targets": active_targets, "active_pointer_errors": pointer_errors,
        },
        "disk_capacity": {**disk, "pressure": pressure},
        "backup_manager": backups,
        "recovery_gate": {
            "backup_integrity_gate": "PASS" if backup_gate else "INCOMPLETE",
            "full_restore_gate": "BLOCKED_NOT_PROVEN",
            "cleanup_authorization": False,
            "reason": "A selective restore is not a full-system recovery drill; no deletion can be authorized from this report.",
        },
        "summary": {
            "keep": sum(x["decision"] == "KEEP" for x in items),
            "review_only": sum(x["decision"] == "REVIEW_ONLY" for x in items),
            "live_referenced": sum(x["dependency_status"] == "BLOCKED_REFERENCED" for x in items),
            "dependency_unknown": sum(x["dependency_status"] == "UNKNOWN_FAIL_CLOSED" for x in items),
            "delete_authorized": 0,
        },
        "items": items,
        "invariants": [
            "No delete, move, truncate, compress, rotate, prune, or service mutation is implemented.",
            "Unknown ownership/dependency/recovery state means KEEP.",
            "Active and rollback release trees, registered worktrees, canonical market data, journals, evidence, backups, and unknown files remain protected.",
            "Gate.io remains the sole canonical market-data/chart/candle/indicator source; cleanup has no market-data or execution authority.",
            "Dropbox quota is monitored through the existing hesdropbox rclone remote; no credentials or passphrase are read into the report.",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit-manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    audit = json.loads(args.audit_manifest.read_text(encoding="utf-8"))
    report = build_manager_report(audit)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("SMART_CLEANUP_AUDIT_OK items={} keep={} review={} delete_authorized=0".format(report["inventory_items"], report["summary"]["keep"], report["summary"]["review_only"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())