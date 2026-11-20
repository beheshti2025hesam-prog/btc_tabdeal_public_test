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

def restore_assessment(evidence: dict[str, Any] | None) -> dict[str, Any]:
    if evidence is None:
        return {"status": "NOT_PROVEN", "full_archive_restore": "NOT_PROVEN",
                "replacement_host_restore": "NOT_PROVEN", "remote_restore": "NOT_RUN",
                "cleanup_authorized": False,
                "reason": "No full-scope restore evidence was supplied."}
    if evidence.get("schema") != "hes_restic_fullscope_restore_drill_v1":
        return {"status": "INVALID_EVIDENCE", "full_archive_restore": "NOT_PROVEN",
                "replacement_host_restore": "NOT_PROVEN", "remote_restore": "NOT_RUN",
                "cleanup_authorized": False, "reason": "Restore evidence schema mismatch."}
    full = evidence.get("full_restore") or {}
    integrity = str(evidence.get("integrity_check") or "")
    required = str(full.get("required_recovery_paths") or "")
    verify = str(full.get("restic_verify") or "")
    try:
        restored_files = int(full.get("restored_files") or 0)
        restored_file_bytes = int(full.get("restored_file_bytes") or 0)
    except (TypeError, ValueError):
        restored_files = restored_file_bytes = 0
    valid = (full.get("status") == "PASS" and integrity.startswith("PASS_READ_DATA_")
             and verify.startswith("PASS_") and required.startswith("PASS_")
             and restored_files > 0 and restored_file_bytes > 0
             and str(full.get("static_content_comparison") or "").startswith("PASS_"))
    if not valid:
        return {"status": "INCOMPLETE_EVIDENCE", "full_archive_restore": "NOT_PROVEN",
                "replacement_host_restore": "NOT_PROVEN", "remote_restore": "NOT_RUN",
                "cleanup_authorized": False,
                "reason": "Restore evidence failed integrity, full-restore, required-path or content checks."}
    return {"status": "FULL_ARCHIVE_RESTORE_VERIFIED", "full_archive_restore": "PASS",
            "restored_files": int(full["restored_files"]),
            "restored_file_bytes": int(full["restored_file_bytes"]),
            "required_recovery_paths": required, "replacement_host_restore": "NOT_PROVEN",
            "remote_restore": "NOT_RUN", "cleanup_authorized": False,
            "reason": "Full archive restored and verified in an isolated same-host directory; replacement-host and remote restore remain separate gates."}


def remote_restore_assessment(evidence: dict[str, Any] | None) -> dict[str, Any]:
    if evidence is None:
        return {"status":"NOT_RUN","cleanup_authorized":False,"reason":"No Dropbox remote-restore drill evidence was supplied."}
    if evidence.get("schema") != "hes_dropbox_core_restore_drill_v1":
        return {"status":"INVALID_EVIDENCE","cleanup_authorized":False,"reason":"Remote restore evidence schema mismatch."}
    r=evidence.get("remote_restore") or {}
    required=("rclone_copy","remote_hash_match","gpg_decrypt","zstd_integrity","tar_safe_path_verification","full_extract","required_core_roots","active_release","rollback_release","main_git_connectivity")
    checks={k:str(r.get(k) or "") for k in required}
    valid=(r.get("status")=="PASS" and all(v.startswith("PASS") for v in checks.values())
           and int(r.get("restored_files") or 0)>0 and int(r.get("restored_file_bytes") or 0)>0
           and str(evidence.get("remote_archive_sha256") or "")==str(evidence.get("manifest_sha256") or ""))
    if not valid:
        return {"status":"INCOMPLETE_EVIDENCE","cleanup_authorized":False,"checks":checks,
                "reason":"Remote copy/hash/decrypt/extract or content verification did not pass."}
    return {"status":"PASS","cleanup_authorized":False,"archive_sha256":evidence.get("remote_archive_sha256"),
            "archive_bytes":evidence.get("remote_archive_bytes"),"restored_files":int(r["restored_files"]),
            "restored_file_bytes":int(r["restored_file_bytes"]),"checks":checks,
            "reason":"Dropbox core copied, hash-matched, decrypted, integrity-checked and fully extracted in an isolated same-host directory."}


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

def archive_inventory(folder: Path, prefix: str = "") -> dict[str, Any]:
    rows, errors = [], 0
    if not folder.is_dir():
        return {"status": "MISSING", "archive_count": 0, "total_bytes": 0, "archives": [], "errors": 1}
    archive_suffixes = (".tar.gz.gpg", ".tar.zst.gpg", ".tar.gz", ".tar.zst", ".bundle")
    for p in sorted(folder.glob(prefix + "*")):
        if not p.is_file() or p.name.endswith((".sha256", ".manifest.txt", ".restore-list")):
            continue
        if not p.name.endswith(archive_suffixes):
            continue
        try:
            size = p.stat().st_size
            fmt = ("zstd+gpg" if p.name.endswith(".tar.zst.gpg") else
                   "gzip+gpg" if p.name.endswith(".tar.gz.gpg") else
                   "git-bundle" if p.name.endswith(".bundle") else
                   "zstd" if p.name.endswith(".tar.zst") else "gzip")
            rows.append({"name": p.name, "size_bytes": size, "format": fmt})
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

def storage_budget(items: list[dict[str, Any]], target_gb: int = 5) -> dict[str, Any]:
    # User's hard storage objective is decimal GB, not GiB: 5 GB = 5,000,000,000 bytes.
    target = int(target_gb) * 1_000_000_000
    project = direct_child_bytes(items, "/opt/hes-trade-agent")
    evidence = direct_child_bytes(items, "/srv/hes-evidence")
    backups = direct_child_bytes(items, "/var/backups/hes-trade-agent")
    core = project + evidence
    total = core + backups
    return {
        "target_gb": target_gb,
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
        "total_local_hes_gb": round(total / 1_000_000_000, 3),
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
                 evidence: dict[str,Any]|None=None,
                 restore_evidence: dict[str,Any]|None=None,
                 remote_restore_evidence: dict[str,Any]|None=None) -> dict[str,Any]:
    now=now or datetime.now(timezone.utc)
    inventory=load_inventory(idlm,cleanup,now)
    local=archive_inventory(BACKUP_ROOT/"encrypted-local")
    offsite=archive_inventory(BACKUP_ROOT/"offsite-staging")
    capacity=disk or disk_state()
    quota=quota or dropbox_quota()
    recovery=restore_assessment(restore_evidence)
    remote_recovery=remote_restore_assessment(remote_restore_evidence)
    recovery["remote_restore"]=remote_recovery["status"]
    recovery["remote_restore_details"]=remote_recovery
    if remote_recovery.get("status") == "PASS" and recovery.get("full_archive_restore") == "PASS":
        recovery["reason"]="Local full restore and Dropbox core restore both passed in isolated same-host drills; replacement-host recovery remains separate and NOT_PROVEN."
    restic_repo = BACKUP_ROOT / "restic-production-v1" / "repo"
    try:
        restic_bytes = int(subprocess.check_output(["du", "-sxB1", str(restic_repo)], text=True).split()[0]) if restic_repo.is_dir() else 0
        restic_status = "READ_OK" if restic_repo.is_dir() else "MISSING"
    except (OSError, subprocess.SubprocessError, ValueError, IndexError):
        restic_bytes, restic_status = 0, "READ_ERROR"
    return {
        "schema":"hes_smart_storage_manager_v1","generated_at":now.isoformat(),
        "mode":"READ_ONLY_CAPACITY_AND_COMPRESSION_PLAN","disk":capacity,
        "inventory_source":"IDLM_V1_PLUS_SMART_CLEANUP_MANAGER_V1",
        "inventory":inventory,
        "recovery_assessment":recovery,
        "summary":{"local_backup":local,"offsite_staging":offsite,
                   "local_restic_repository":{"status":restic_status,"allocated_bytes":restic_bytes},
                   "dropbox_quota":quota},
        "storage_budget":storage_budget(cleanup.get("items", []), target_gb=5),
        "compression":compression_advice(evidence),
        "policy":{"canonical_market_data":"Gate.io Public Spot BTC_USDT",
          "backup_destination":"encrypted Dropbox","backup_retention":"unchanged until remote restore and replacement-host recovery gates pass",
          "unknown_or_unverified":"KEEP","deletion_authorized":False,"move_authorized":False,
          "compression_authorized":False,"automatic_cleanup_timer_authorized":False,
          "safe_cache_maintenance_timer_enabled":True,
          "automatic_project_data_cleanup_authorized":False,
          "full_archive_restore_verified":recovery.get("full_archive_restore") == "PASS",
          "remote_restore_verified":remote_recovery.get("status") == "PASS",
          "replacement_host_restore_proven":False,
          "local_footprint_target_gb":5,
          "local_footprint_target_bytes":5_000_000_000},
        "invariants":["Uses the existing IDLM and dependency-aware Smart Cleanup inventories; does not rescan project trees.",
          "No file is deleted, moved, truncated, rotated, pruned or compressed by this report.",
          "All backups and active/rollback releases remain protected.",
          "New compression format must be versioned; legacy gzip archives remain readable and retained.",
          "Dropbox free quota is a hard budget; never upload an unbounded second copy or exceed the free tier.",
          "The daily timer only removes stale regenerable pip build caches and bounds APT/journald caches; project/release/worktree/data/evidence/backup deletion remains disabled.",
          "Full archive restore and Dropbox remote-core restore are distinct from replacement-host recovery; replacement-host recovery and explicit approval remain required before backup retention or cleanup authorization."]}

def main() -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--idlm-report",type=Path,required=True)
    parser.add_argument("--cleanup-report",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--compression-evidence",type=Path)
    parser.add_argument("--restore-evidence",type=Path)
    parser.add_argument("--remote-restore-evidence",type=Path)
    parser.add_argument("--target-gb",type=int,default=5,help="Decimal GB budget for complete local HES footprint (default: 5)")
    args=parser.parse_args()
    idlm=json.loads(args.idlm_report.read_text())
    cleanup=json.loads(args.cleanup_report.read_text())
    evidence=json.loads(args.compression_evidence.read_text()) if args.compression_evidence else None
    restore_evidence=json.loads(args.restore_evidence.read_text()) if args.restore_evidence else None
    remote_restore_evidence=json.loads(args.remote_restore_evidence.read_text()) if args.remote_restore_evidence else None
    report=build_report(idlm=idlm,cleanup=cleanup,evidence=evidence,restore_evidence=restore_evidence,remote_restore_evidence=remote_restore_evidence)
    report["storage_budget"]=storage_budget(cleanup.get("items", []), target_gb=args.target_gb)
    report["policy"]["local_footprint_target_gb"]=args.target_gb
    report["policy"]["local_footprint_target_bytes"]=args.target_gb*1_000_000_000
    args.output.parent.mkdir(parents=True,exist_ok=True)
    tmp=args.output.with_suffix(args.output.suffix+".partial")
    tmp.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    tmp.replace(args.output)
    print("SMART_STORAGE_PLAN_OK inventory_source=IDLM+SMART_CLEANUP deletion_authorized=false compression_authorized=false")
    return 0

if __name__=="__main__": raise SystemExit(main())