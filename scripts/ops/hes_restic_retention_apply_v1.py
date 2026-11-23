#!/usr/bin/env python3
"""Apply only full-scope Restic retention candidates after a fresh restore drill."""
from __future__ import annotations
import argparse
from datetime import date, datetime, timezone
import json
import re
import subprocess
from pathlib import Path
from typing import Any

try:
    from .hes_restic_retention_plan_v1 import EXPECTED_HOST, EXPECTED_TAG, REQUIRED_FULL_PATHS, plan_retention
except ImportError:
    from hes_restic_retention_plan_v1 import EXPECTED_HOST, EXPECTED_TAG, REQUIRED_FULL_PATHS, plan_retention

MARKER_SCHEMA = "hes_restic_restore_verification_v1"
CONFIRM_TOKEN = "HES_RESTIC_RETENTION_APPLY_V1"
EXPECTED_STRATEGY_REF = "refs/heads/feat/strategy-opportunity-diagnostic-v1"
REQUIRED_CHECKS = (
    "restic_restore", "release_manifest_hashes", "release_file_hashes",
    "git_strategy_ref", "host_config", "evidence_sample", "sentinelx_audit_log",
)
REPLACEMENT_ATTESTATION_SCHEMA = "hes_replacement_host_restore_attestation_v1"
REQUIRED_REPLACEMENT_CHECKS = (
    "repository_open", "key_unlocked", "full_scope_restore", "release_manifests",
    "git_strategy_ref", "host_config", "journals_and_evidence", "boot_smoke_test",
)


def verify_replacement_attestation_signature(
    attestation_path: Path, signature_path: Path, public_key_path: Path,
) -> tuple[bool, str]:
    if not attestation_path.is_file() or not signature_path.is_file() or not public_key_path.is_file():
        return False, "attestation_signature_or_pinned_public_key_missing"
    result = subprocess.run(
        ["openssl", "pkeyutl", "-verify", "-pubin", "-inkey", str(public_key_path),
         "-sigfile", str(signature_path), "-in", str(attestation_path), "-rawin"],
        check=False, capture_output=True, text=True,
    )
    if result.returncode != 0:
        return False, "replacement_host_attestation_signature_invalid"
    return True, "signature_verified"


def validate_replacement_host_attestation(
    attestation_path: Path,
    signature_path: Path,
    public_key_path: Path,
    latest_full_snapshot_id: str,
    latest_snapshot_paths: list[str],
    now: datetime | None = None,
    signature_verifier=verify_replacement_attestation_signature,
) -> tuple[bool, str]:
    now = now or datetime.now(timezone.utc)
    valid_signature, signature_reason = signature_verifier(attestation_path, signature_path, public_key_path)
    if not valid_signature:
        return False, signature_reason
    try:
        attestation = json.loads(attestation_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False, "replacement_host_attestation_json_invalid"
    if attestation.get("schema") != REPLACEMENT_ATTESTATION_SCHEMA or attestation.get("status") != "PASS":
        return False, "replacement_host_attestation_schema_or_status_invalid"
    if attestation.get("source_snapshot_id") != latest_full_snapshot_id:
        return False, "replacement_host_attestation_snapshot_mismatch"
    if attestation.get("source_host") != EXPECTED_HOST:
        return False, "replacement_host_attestation_source_host_mismatch"
    recovery_host = str(attestation.get("recovery_host_id", "")).strip()
    fingerprint = str(attestation.get("recovery_host_fingerprint", "")).strip()
    if not recovery_host or recovery_host == EXPECTED_HOST or len(fingerprint) < 32:
        return False, "replacement_host_identity_not_independent_or_unverified"
    try:
        created = datetime.fromisoformat(str(attestation.get("created_at_utc", "")).replace("Z", "+00:00"))
    except ValueError:
        return False, "replacement_host_attestation_timestamp_invalid"
    if created.tzinfo is None:
        return False, "replacement_host_attestation_timestamp_missing_timezone"
    age_seconds = (now - created.astimezone(timezone.utc)).total_seconds()
    if age_seconds < -300 or age_seconds > 86400:
        return False, "replacement_host_attestation_stale_or_future_dated"
    checks = attestation.get("checks", {})
    if not isinstance(checks, dict) or any(checks.get(name) != "PASS" for name in REQUIRED_REPLACEMENT_CHECKS):
        return False, "replacement_host_restore_checks_incomplete"
    restored_roots = attestation.get("restored_roots")
    if not isinstance(restored_roots, list) or set(restored_roots) != set(latest_snapshot_paths):
        return False, "replacement_host_restored_root_set_mismatch"
    try:
        restored_file_count = int(attestation.get("restored_file_count", 0))
        restored_bytes = int(attestation.get("restored_bytes", 0))
    except (TypeError, ValueError):
        return False, "replacement_host_restore_inventory_invalid"
    if restored_file_count <= 0 or restored_bytes <= 0:
        return False, "replacement_host_restore_inventory_missing"
    for field in ("archive_sha256", "restore_manifest_sha256"):
        value = str(attestation.get(field, ""))
        if not re.fullmatch(r"[0-9a-fA-F]{64}", value):
            return False, f"replacement_host_{field}_invalid"
    if not str(attestation.get("restic_version", "")).strip():
        return False, "replacement_host_restic_version_missing"
    return True, "replacement_host_restore_attestation_verified"


def validate_marker(marker: dict[str, Any], latest_full_snapshot_id: str, now: datetime | None = None) -> None:
    now = now or datetime.now(timezone.utc)
    if marker.get("schema") != MARKER_SCHEMA or marker.get("status") != "PASS":
        raise ValueError("restore verification marker missing or invalid")
    if marker.get("snapshot_id") != latest_full_snapshot_id:
        raise ValueError("restore marker does not match the latest full-scope snapshot")
    created = datetime.fromisoformat(str(marker.get("created_at_utc", "")).replace("Z", "+00:00"))
    age_seconds = (now - created.astimezone(timezone.utc)).total_seconds() if created.tzinfo else None
    if age_seconds is None or age_seconds < -300 or age_seconds > 86400:
        raise ValueError("restore verification marker is stale, future-dated, or has an invalid timestamp")
    checks = marker.get("checks", {})
    failed = [name for name in REQUIRED_CHECKS if checks.get(name) != "PASS"]
    if failed:
        raise ValueError("restore verification checks failed: " + ",".join(failed))
    if marker.get("strategy_ref") != EXPECTED_STRATEGY_REF:
        raise ValueError("restore marker lacks the required strategy research ref")
    commit = str(marker.get("strategy_commit", ""))
    if len(commit) != 40 or any(ch not in "0123456789abcdef" for ch in commit.lower()):
        raise ValueError("restore marker lacks a valid verified strategy commit")
    if int(marker.get("release_files_verified", 0)) <= 0:
        raise ValueError("restore marker lacks verified release file inventory")
    if len(str(marker.get("evidence_sha256", ""))) != 64:
        raise ValueError("restore marker lacks a verified evidence SHA")


def eligible_delete_ids(plan: dict[str, Any], marker: dict[str, Any], confirm: str, now: datetime | None = None) -> list[str]:
    if confirm != CONFIRM_TOKEN:
        raise ValueError("explicit retention confirmation token missing")
    latest = plan.get("latest_full_snapshot_id")
    validate_marker(marker, str(latest or ""), now)
    keep_ids = {str(row.get("snapshot_id")) for row in plan.get("keep", [])}
    ids = []
    for row in plan.get("delete_candidates", []):
        sid = str(row.get("snapshot_id", ""))
        if not sid or sid in keep_ids:
            raise ValueError("invalid or overlapping retention candidate")
        ids.append(sid)
    return sorted(set(ids))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--marker", type=Path, required=True)
    ap.add_argument("--confirm", required=True)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--replacement-host-attestation", type=Path, default=Path("/var/lib/hes-operational-health/replacement-host-restore-attestation.json"))
    ap.add_argument("--replacement-host-signature", type=Path, default=Path("/var/lib/hes-operational-health/replacement-host-restore-attestation.sig"))
    ap.add_argument("--replacement-host-public-key", type=Path, default=Path("/etc/hes-trade-agent/recovery-attestation.pub"))
    ap.add_argument("--today", type=date.fromisoformat, default=datetime.now(timezone.utc).date())
    ns = ap.parse_args()
    marker = json.loads(ns.marker.read_text(encoding="utf-8"))
    snapshots = json.loads(subprocess.run(["restic", "snapshots", "--json"], check=True, capture_output=True, text=True).stdout)
    plan = plan_retention(snapshots, ns.today)
    ids = eligible_delete_ids(plan, marker, ns.confirm)
    if not ids:
        subprocess.run(["restic", "check", "--read-data-subset=1/20"], check=True)
        print("RESTIC_RETENTION_NO_DELETE_CANDIDATES latest=" + str(plan.get("latest_full_snapshot_id")) + " integrity_check=PASS")
        return 0
    # Fail closed if any candidate is not an exact full-scope snapshot for this host/tag.
    by_id = {str(s.get("id")): s for s in snapshots}
    for sid in ids:
        snap = by_id.get(sid)
        if (not snap or snap.get("hostname") != EXPECTED_HOST
                or EXPECTED_TAG not in (snap.get("tags") or [])
                or set(snap.get("paths") or []) != set(REQUIRED_FULL_PATHS)):
            raise ValueError("retention candidate is not a full-scope HES snapshot: " + sid)
    latest_snapshot = by_id[str(plan["latest_full_snapshot_id"])]
    attestation_ok, attestation_reason = validate_replacement_host_attestation(
        ns.replacement_host_attestation, ns.replacement_host_signature,
        ns.replacement_host_public_key, str(plan["latest_full_snapshot_id"]),
        list(latest_snapshot.get("paths") or []),
    )
    if ns.dry_run:
        print(json.dumps({"status": "DRY_RUN", "latest_full_snapshot_id": plan["latest_full_snapshot_id"],
                          "delete_ids": ids, "replacement_host_attestation": attestation_reason}, sort_keys=True))
        return 0
    if not attestation_ok:
        subprocess.run(["restic", "check", "--read-data-subset=1/20"], check=True)
        print("RESTIC_RETENTION_BLOCKED_REPLACEMENT_HOST_PROOF reason=" + attestation_reason
              + " latest=" + str(plan.get("latest_full_snapshot_id")) + " candidates=" + str(len(ids)))
        return 0
    subprocess.run(["restic", "forget", *ids, "--prune"], check=True)
    subprocess.run(["restic", "check", "--read-data-subset=1/20"], check=True)
    report = {
        "schema": "hes_restic_retention_apply_v1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "latest_full_snapshot_id": plan["latest_full_snapshot_id"],
        "deleted_snapshot_ids": ids,
        "restore_marker": str(ns.marker),
        "partial_and_out_of_scope_snapshots": "preserved",
        "post_prune_check": "PASS",
    }
    outdir = Path("/var/lib/hes-operational-health/restic-retention")
    outdir.mkdir(parents=True, exist_ok=True)
    out = outdir / ("restic-retention-apply-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + ".json")
    out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, sort_keys=True))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())