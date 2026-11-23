#!/usr/bin/env python3
"""Perform an isolated, hash-verified restore drill for a full HES Restic snapshot."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from typing import Any

SCHEMA = "hes_restic_restore_verification_v1"
STRATEGY_REF_DEFAULT = "refs/heads/feat/strategy-opportunity-diagnostic-v1"
DEFAULT_SAFETY_MARGIN_BYTES = 1024 * 1024 * 1024
DEFAULT_SAFETY_MARGIN_PERCENT = 10


class InsufficientRestoreSpace(RuntimeError):
    def __init__(self, report: dict[str, Any]):
        super().__init__("insufficient free disk space for isolated restore drill")
        self.report = report


def restore_space_preflight(
    snapshot_id: str,
    temp_parent: Path,
    *,
    safety_margin_bytes: int = DEFAULT_SAFETY_MARGIN_BYTES,
    safety_margin_percent: int = DEFAULT_SAFETY_MARGIN_PERCENT,
) -> dict[str, Any]:
    """Conservatively preflight a full-snapshot restore before creating temp files.

    Restic's restore-size includes the whole snapshot, while this drill restores
    selected roots only; using the full size deliberately errs on the safe side.
    """
    if not temp_parent.is_dir():
        raise ValueError(f"restore temp parent is not a directory: {temp_parent}")
    result = subprocess.run(
        ["restic", "stats", snapshot_id, "--mode", "restore-size", "--json"],
        check=True, capture_output=True, text=True,
    )
    stats = json.loads(result.stdout)
    restore_bytes = int(stats.get("total_size", 0))
    if restore_bytes <= 0:
        raise ValueError("Restic restore-size estimate missing or invalid")
    free_bytes = shutil.disk_usage(temp_parent).free
    margin = max(int(safety_margin_bytes), (restore_bytes * int(safety_margin_percent) + 99) // 100)
    required_bytes = restore_bytes + margin
    return {
        "status": "PASS" if free_bytes >= required_bytes else "DEFERRED_INSUFFICIENT_SPACE",
        "snapshot_id": snapshot_id,
        "restore_size_bytes": restore_bytes,
        "safety_margin_bytes": margin,
        "required_free_bytes": required_bytes,
        "available_free_bytes": free_bytes,
        "temp_parent": str(temp_parent),
        "estimate_scope": "FULL_SNAPSHOT_CONSERVATIVE_UPPER_BOUND",
    }


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_release_manifest(release_root: Path) -> dict[str, Any]:
    candidates = [
        release_root / "HES_RELEASE_MANIFEST_v1.json",
        *sorted(release_root.glob("RELEASE_MANIFEST_*.json")),
    ]
    manifest_path = next((p for p in candidates if p.is_file()), None)
    if manifest_path is None:
        raise ValueError(f"release manifest missing: {release_root}")
    sidecar = manifest_path.with_suffix(".sha256")
    if not sidecar.is_file():
        raise ValueError(f"release manifest SHA sidecar missing: {sidecar}")
    digest = sha256_file(manifest_path)
    if sidecar.read_text(encoding="utf-8").split()[0] != digest:
        raise ValueError(f"release manifest SHA mismatch: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    expected_commit = manifest.get("commit_sha") or manifest.get("source_commit")
    if expected_commit and expected_commit != release_root.name:
        raise ValueError(f"release commit mismatch: {release_root}")
    entries = manifest.get("files")
    if not isinstance(entries, list) or manifest.get("file_count") != len(entries):
        raise ValueError(f"release manifest file inventory mismatch: {manifest_path}")
    for item in entries:
        rel = Path(str(item.get("path", "")))
        if not rel.parts or rel.is_absolute() or ".." in rel.parts:
            raise ValueError(f"unsafe release manifest path: {rel}")
        target = release_root / rel
        if not target.is_file():
            raise ValueError(f"release file missing after restore: {target}")
        if sha256_file(target) != item.get("sha256"):
            raise ValueError(f"release file SHA mismatch: {target}")
    return {"release": release_root.name, "files_verified": len(entries), "manifest_sha256": digest}


def verify_restored_tree(
    restore_root: Path,
    active_release: str,
    rollback_release: str,
    dashboard_release: str,
    strategy_ref: str,
    strategy_commit: str,
    evidence_sample: str,
    evidence_sha256: str,
) -> dict[str, Any]:
    release_results = []
    for raw in (active_release, rollback_release, dashboard_release):
        release_root = restore_root / raw.lstrip("/")
        release_results.append(verify_release_manifest(release_root))
    git_dir = restore_root / "opt/hes-trade-agent/.git"
    if not git_dir.is_dir():
        raise ValueError("restored Git object store missing")
    ref = subprocess.run(
        ["git", "--git-dir", str(git_dir), "show-ref", "--verify", strategy_ref],
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    restored_commit = ref.split()[0]
    if restored_commit != strategy_commit:
        raise ValueError("restored strategy branch commit mismatch")
    object_type = subprocess.run(
        ["git", "--git-dir", str(git_dir), "cat-file", "-t", strategy_commit],
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    if object_type != "commit":
        raise ValueError("strategy ref does not resolve to a commit object")
    config_root = restore_root / "etc/hes-trade-agent"
    if not config_root.is_dir() or not any(config_root.rglob("*")):
        raise ValueError("restored HES host configuration missing or empty")
    evidence_path = restore_root / evidence_sample.lstrip("/")
    if not evidence_path.is_file() or sha256_file(evidence_path) != evidence_sha256:
        raise ValueError("restored evidence sample missing or SHA mismatch")
    audit_path = restore_root / "var/lib/sentinelx/audit.jsonl"
    if not audit_path.is_file() or audit_path.stat().st_size == 0:
        raise ValueError("restored SentinelX audit evidence missing or empty")
    return {
        "release_results": release_results,
        "release_files_verified": sum(x["files_verified"] for x in release_results),
        "strategy_ref": strategy_ref,
        "strategy_commit": restored_commit,
        "host_config": "PASS",
        "evidence_sample": evidence_sample,
        "evidence_sha256": evidence_sha256,
        "audit_log_bytes": audit_path.stat().st_size,
    }


def run_drill(args: argparse.Namespace) -> dict[str, Any]:
    space = restore_space_preflight(
        args.snapshot_id, Path(args.temp_parent),
        safety_margin_bytes=args.safety_margin_bytes,
        safety_margin_percent=args.safety_margin_percent,
    )
    if space["status"] != "PASS":
        raise InsufficientRestoreSpace(space)
    evidence_source = Path(args.evidence_sample)
    if not evidence_source.is_file():
        raise ValueError(f"evidence sample unavailable: {evidence_source}")
    evidence_sha = sha256_file(evidence_source)
    work = Path(tempfile.mkdtemp(prefix="hes-restic-restore-drill-", dir=args.temp_parent))
    try:
        target = work / "restore"
        includes = [
            args.active_release, args.rollback_release, args.dashboard_release,
            "/opt/hes-trade-agent/.git", "/etc/hes-trade-agent",
            "/var/lib/sentinelx/audit.jsonl", args.evidence_sample,
        ]
        command = ["restic", "restore", args.snapshot_id, "--target", str(target)]
        for path in includes:
            command.extend(["--include", path])
        subprocess.run(command, check=True)
        verified = verify_restored_tree(
            target, args.active_release, args.rollback_release, args.dashboard_release,
            args.strategy_ref, args.strategy_commit, args.evidence_sample, evidence_sha,
        )
        marker = {
            "schema": SCHEMA,
            "status": "PASS",
            "snapshot_id": args.snapshot_id,
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "restore_space_preflight": space,
            "checks": {
                "restic_restore": "PASS",
                "release_manifest_hashes": "PASS",
                "release_file_hashes": "PASS",
                "git_strategy_ref": "PASS",
                "host_config": "PASS",
                "evidence_sample": "PASS",
                "sentinelx_audit_log": "PASS",
            },
            **verified,
        }
        marker_path = Path(args.marker)
        marker_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = marker_path.with_suffix(marker_path.suffix + ".tmp")
        tmp.write_text(json.dumps(marker, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.chmod(tmp, 0o600)
        tmp.replace(marker_path)
        return marker
    finally:
        shutil.rmtree(work, ignore_errors=True)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--snapshot-id", required=True)
    ap.add_argument("--active-release", required=True)
    ap.add_argument("--rollback-release", required=True)
    ap.add_argument("--dashboard-release", required=True)
    ap.add_argument("--strategy-ref", default=STRATEGY_REF_DEFAULT)
    ap.add_argument("--strategy-commit", required=True)
    ap.add_argument("--evidence-sample", required=True)
    ap.add_argument("--marker", default="/var/lib/hes-operational-health/restic-restore-verification.json")
    ap.add_argument("--temp-parent", default="/var/tmp")
    ap.add_argument("--safety-margin-bytes", type=int, default=DEFAULT_SAFETY_MARGIN_BYTES)
    ap.add_argument("--safety-margin-percent", type=int, default=DEFAULT_SAFETY_MARGIN_PERCENT)
    args = ap.parse_args()
    try:
        marker = run_drill(args)
    except InsufficientRestoreSpace as exc:
        print("RESTIC_RESTORE_DRILL_DEFERRED_INSUFFICIENT_SPACE " + json.dumps(exc.report, sort_keys=True))
        return 75
    print("RESTIC_RESTORE_DRILL_PASS snapshot=" + marker["snapshot_id"]
          + " release_files=" + str(marker["release_files_verified"])
          + " strategy_commit=" + marker["strategy_commit"]
          + " marker=" + args.marker)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())