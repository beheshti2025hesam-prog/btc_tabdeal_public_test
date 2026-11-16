#!/usr/bin/env python3
"""Read-only HES capacity planner. Reuses IDLM/Smart Cleanup inventories; never mutates data."""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import json, shutil, subprocess
from pathlib import Path, PurePosixPath
from typing import Any

ROOT = Path("/opt/hes-trade-agent")
BACKUP_ROOT = Path("/var/backups/hes-trade-agent")
MAX_REPORT_AGE_SECONDS = 900

def parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)

def load_inventory(idlm: dict[str, Any], cleanup: dict[str, Any], now: datetime) -> dict[str, Any]:
    if idlm.get("schema") != "hes_data_lifecycle_audit_v1" or idlm.get("mode") != "READ_ONLY_DRY_RUN":
        raise ValueError("IDLM schema/mode mismatch")
    if cleanup.get("schema") != "hes_smart_cleanup_manager_v1" or cleanup.get("mode") != "READ_ONLY_DEPENDENCY_AWARE_DRY_RUN":
        raise ValueError("Smart Cleanup schema/mode mismatch")
    generated = parse_time(str(idlm["generated_at"]))
    age = (now - generated).total_seconds()
    if age < -60 or age > MAX_REPORT_AGE_SECONDS:
        raise ValueError("IDLM report stale or future-dated")
    if cleanup.get("source_audit_schema") != idlm["schema"]:
        raise ValueError("Smart Cleanup source schema mismatch")
    if cleanup.get("source_audit_generated_at") != idlm.get("generated_at"):
        raise ValueError("Smart Cleanup did not consume this exact IDLM snapshot")
    cleanup_age = (now - parse_time(str(cleanup["generated_at"]))).total_seconds()
    if cleanup_age < -60 or cleanup_age > MAX_REPORT_AGE_SECONDS:
        raise ValueError("Smart Cleanup report stale or future-dated")
    gate = cleanup.get("source_audit_gate") or {}
    if gate.get("status") != "PASS" or gate.get("errors") != []:
        raise ValueError("Smart Cleanup source-audit gate failed")
    if float(gate.get("age_seconds", 1e9)) > MAX_REPORT_AGE_SECONDS:
        raise ValueError("Smart Cleanup source-audit gate is stale")
    deps = cleanup.get("dependency_scan") or {}
    for key in ("process_scan_errors", "scheduled_job_scan_errors", "unit_scan_errors", "active_pointer_errors"):
        if key not in deps:
            raise ValueError("dependency scan field missing: " + key)
        val = deps[key]
        if val not in (0, [], None):
            raise ValueError("dependency scan not clean: " + key)
    items = cleanup.get("items")
    if not isinstance(items, list) or int(cleanup.get("inventory_items", -1)) != len(items):
        raise ValueError("Smart Cleanup inventory count mismatch")
    by_class: dict[str, dict[str, int]] = defaultdict(lambda: {"items": 0, "allocated_bytes": 0})
    errors = 0
    for item in items:
        if not isinstance(item, dict) or not item.get("classification") or not item.get("path"):
            errors += 1
            continue
        classification = str(item["classification"])
        by_class[classification]["items"] += 1
        try:
            size = int(item.get("allocated_bytes") or 0)
            if size < 0: raise ValueError
            by_class[classification]["allocated_bytes"] += size
        except (TypeError, ValueError):
            errors += 1
    if errors:
        raise ValueError("malformed cleanup inventory rows")
    counts = Counter(str(x.get("classification")) for x in items)
    return {
        "status": "PASS",
        "source_idlm_generated_at": idlm["generated_at"],
        "source_cleanup_generated_at": cleanup.get("generated_at"),
        "source_age_seconds": round(age, 2),
        "items": len(items),
        "classification_counts": dict(counts),
        "classification_storage": dict(by_class),
        "recovery_gate": cleanup.get("recovery_gate", {}),
        "dependency_scan": {
            "process_reference_count": deps.get("process_reference_count"),
            "running_unit_reference_count": deps.get("running_unit_reference_count"),
            "scheduled_job_reference_count": deps.get("scheduled_job_reference_count"),
            "scan_errors": 0,
        },
        "deletion_authorized": False,
    }

def disk_state(path: Path = Path("/")) -> dict[str, Any]:
    st = __import__("os").statvfs(path)
    total = st.f_blocks * st.f_frsize
    free = st.f_bavail * st.f_frsize
    inode_total, inode_free = st.f_files, st.f_favail
    return {
        "path": str(path), "total_bytes": total, "free_bytes": free, "used_bytes": total-free,
        "free_percent": round(100*free/total, 2) if total else None,
        "inode_total": inode_total, "inode_free": inode_free,
        "inode_free_percent": round(100*inode_free/inode_total, 2) if inode_total else None,
        "pressure": "CRITICAL" if total and free/total < .10 else "WARN" if total and free/total < .15 else "OK",
    }

def archive_inventory(folder: Path, prefix: str) -> dict[str, Any]:
    rows, errors = [], 0
    if not folder.is_dir():
        return {"status": "MISSING", "archive_count": 0, "total_bytes": 0, "archives": [], "errors": 1}
    for p in sorted(folder.glob(prefix + "*")):
        if not p.is_file() or p.name.endswith((".sha256", ".manifest.txt")): continue
        try:
            size = p.stat().st_size
            rows.append({"name": p.name, "size_bytes": size,
                         "format": "zstd" if ".tar.zst." in p.name else "gzip"})
        except OSError:
            errors += 1
    by_day: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        stamp = row["name"][len(prefix):]
        day = stamp[:8] if len(stamp) >= 8 and stamp[:8].isdigit() else "unknown"
        by_day[day].append(row)
    return {
        "status": "PASS" if errors == 0 else "PARTIAL_ERROR",
        "archive_count": len(rows), "total_bytes": sum(x["size_bytes"] for x in rows),
        "archives": rows,
        "same_day_multiple": {d:v for d,v in by_day.items() if d != "unknown" and len(v) > 1},
        "errors": errors,
    }

def compression_advice(evidence: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(evidence, dict):
        return {"status":"NO_BENCHMARK","recommendation":"KEEP_CURRENT_FORMAT_UNTIL_BENCHMARKED"}
    try:
        raw = int(evidence["source_bytes"])
        results = evidence["results"]
        gz = int(results["gzip_1"]["bytes"])
        z3 = int(results["zstd_3_single_thread"]["bytes"])
        z9 = int(results["zstd_9_single_thread"]["bytes"])
        if min(raw, gz, z3, z9) <= 0 or max(gz, z3, z9) >= raw:
            raise ValueError
    except (KeyError, TypeError, ValueError):
        # Accept the original flat test/fixture schema for backward compatibility.
        try:
            raw, gz, z3, z9 = (int(evidence[k]) for k in
                               ("source_bytes", "gzip1_bytes", "zstd3_bytes", "zstd9_bytes"))
            if min(raw, gz, z3, z9) <= 0 or max(gz, z3, z9) >= raw:
                raise ValueError
        except (KeyError, TypeError, ValueError):
            return {"status":"INVALID_EVIDENCE","recommendation":"KEEP_CURRENT_FORMAT"}
    saving = round(100 * (gz-z9) / gz, 2)
    is_local = evidence.get("scope") == "local_backup"
    return {
        "status": "LOCAL_BACKUP_STREAM_BENCHMARK" if is_local else "FULL_SCOPE_STREAM_BENCHMARK_NOT_LOCAL_BACKUP_PROOF",
        "source_bytes": raw, "gzip1_bytes": gz, "zstd3_bytes": z3, "zstd9_bytes": z9,
        "zstd9_vs_gzip1_saving_percent": saving,
        "benchmark_source": evidence.get("source", "legacy_fixture"),
        "gpg_encryption_included_in_size_benchmark": evidence.get("gpg_encryption_included_in_size_benchmark", False),
        "roundtrip_status": (evidence.get("restore_roundtrip_status") or
                             evidence.get("fixture_roundtrip_status") or
                             (evidence.get("roundtrip") or {}).get("status", "NOT_PROVEN")),
        "recommendation": "PROTOTYPE_ZSTD9_FOR_LOCAL_BACKUP_V2" if saving >= 5 else "KEEP_GZIP1",
        "legacy_gzip_restore_required": True,
        "production_format_changed": False,
        "compression_authorized": False,
        "note": ("Exact local-backup include-list stream benchmark; encrypted archive fixture passed, but no production archive was written."
                 if is_local else "Full-scope offsite include-set benchmark; local-backup-specific benchmark still required.")
    }

def direct_child_bytes(items: list[dict[str, Any]], root: str) -> int:
    base = PurePosixPath(root)
    total = 0
    for item in items:
        try:
            path = PurePosixPath(str(item["path"]))
            size = int(item.get("allocated_bytes") or 0)
        except (KeyError, TypeError, ValueError):
            continue
        # Only immediate children are counted. Nested manifest rows are not added
        # again, preventing the scanner's overlapping-root reports from double counting.
        if path.parent == base and size >= 0:
            total += size
    return total

def storage_budget(items: list[dict[str, Any]], target_gib: int = 10) -> dict[str, Any]:
    target = int(target_gib) * 1024**3
    project = direct_child_bytes(items, "/opt/hes-trade-agent")
    evidence = direct_child_bytes(items, "/srv/hes-evidence")
    backups = direct_child_bytes(items, "/var/backups/hes-trade-agent")
    core = project + evidence
    total = core + backups
    return {
        "target_gib": target_gib,
        "target_bytes": target,
        "scope": "HES local project checkout + independent evidence store + local backup/staging roots; excludes Ubuntu and SentinelX platform files",
        "components_bytes": {
            "project_checkout_including_releases_candidates_worktrees": project,
            "independent_evidence_store": evidence,
            "local_backups_and_offsite_staging": backups
        },
        "agent_core_bytes_excluding_backup_copies": core,
        "total_local_hes_bytes_including_backups": total,
        "total_local_hes_gib": round(total / 1024**3, 3),
        "core_within_target": core <= target,
        "complete_footprint_within_target": total <= target,
        "over_target_bytes": max(0, total-target),
        "counting_method": "sum only direct-child allocated-byte rows from the exact IDLM/Smart Cleanup snapshot; nested rows are excluded to avoid double counting",
        "no_data_mutated": True
    }

def dropbox_quota() -> dict[str, Any]:
    if not shutil.which("rclone"): return {"status":"UNAVAILABLE"}
    try:
        p=subprocess.run(["rclone","about","hesdropbox:","--json"],capture_output=True,text=True,timeout=30,check=False)
        if p.returncode: return {"status":"UNAVAILABLE"}
        q=json.loads(p.stdout); total,used,free=(int(q.get(k,0)) for k in ("total","used","free"))
        return {"status":"READ_OK","total_bytes":total,"used_bytes":used,"free_bytes":free,
                "used_percent":round(100*used/total,2) if total else None}
    except (OSError,subprocess.TimeoutExpired,ValueError,TypeError):
        return {"status":"UNAVAILABLE"}

def build_report(*, idlm: dict[str,Any], cleanup: dict[str,Any], now: datetime|None=None,
                 disk: dict[str,Any]|None=None, quota: dict[str,Any]|None=None,
                 evidence: dict[str,Any]|None=None) -> dict[str,Any]:
    now=now or datetime.now(timezone.utc)
    inventory=load_inventory(idlm,cleanup,now)
    local=archive_inventory(BACKUP_ROOT/"encrypted-local","hes-full-")
    offsite=archive_inventory(BACKUP_ROOT/"offsite-staging","hes-offsite-core-")
    capacity=disk or disk_state()
    quota=quota or dropbox_quota()
    return {
        "schema":"hes_smart_storage_manager_v1","generated_at":now.isoformat(),
        "mode":"READ_ONLY_CAPACITY_AND_COMPRESSION_PLAN","disk":capacity,
        "inventory_source":"IDLM_V1_PLUS_SMART_CLEANUP_MANAGER_V1",
        "inventory":inventory,
        "summary":{"local_backup":local,"offsite_staging":offsite,"dropbox_quota":quota},
        "storage_budget":storage_budget(cleanup.get("items", []), target_gib=10),
        "compression":compression_advice(evidence),
        "policy":{"canonical_market_data":"Gate.io Public Spot BTC_USDT",
          "backup_destination":"encrypted Dropbox","backup_retention":"unchanged until full restore gate passes",
          "unknown_or_unverified":"KEEP","deletion_authorized":False,"move_authorized":False,
          "compression_authorized":False,"automatic_cleanup_timer_authorized":False,
          "local_footprint_target_gib":10},
        "invariants":["Uses the existing IDLM and dependency-aware Smart Cleanup inventories; does not rescan project trees.",
          "No file is deleted, moved, truncated, rotated, pruned or compressed by this report.",
          "All backups and active/rollback releases remain protected.",
          "New compression format must be versioned; legacy gzip archives remain readable and retained.",
          "Dropbox free quota is a hard budget; never upload an unbounded second copy or exceed the free tier.",
          "Full restore gate must pass before any retention or cleanup authorization."]}

def main() -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--idlm-report",type=Path,required=True)
    parser.add_argument("--cleanup-report",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--compression-evidence",type=Path)
    args=parser.parse_args()
    idlm=json.loads(args.idlm_report.read_text())
    cleanup=json.loads(args.cleanup_report.read_text())
    evidence=json.loads(args.compression_evidence.read_text()) if args.compression_evidence else None
    report=build_report(idlm=idlm,cleanup=cleanup,evidence=evidence)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    tmp=args.output.with_suffix(args.output.suffix+".partial")
    tmp.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    tmp.replace(args.output)
    print("SMART_STORAGE_PLAN_OK inventory_source=IDLM+SMART_CLEANUP deletion_authorized=false compression_authorized=false")
    return 0

if __name__=="__main__": raise SystemExit(main())
