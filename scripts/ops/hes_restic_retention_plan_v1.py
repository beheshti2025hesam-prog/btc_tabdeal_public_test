#!/usr/bin/env python3
"""Read-only, full-scope-aware retention planner for HES Restic snapshots."""
from __future__ import annotations
import argparse
from datetime import date, datetime, timezone
import json
from pathlib import Path
from typing import Any

POLICY = {"daily_days": 7, "weekly_sunday_days": 28, "monthly_first_day_days": 180}
EXPECTED_TAG = "hes-full-recovery-v1"
EXPECTED_HOST = "hes-vps-recovery-v1"
REQUIRED_FULL_PATHS = frozenset({
    "/etc/apt", "/etc/cloud", "/etc/cron.d", "/etc/cron.daily",
    "/etc/cron.hourly", "/etc/cron.weekly", "/etc/environment", "/etc/fstab",
    "/etc/hes-trade-agent", "/etc/hostname", "/etc/hosts", "/etc/logrotate.d",
    "/etc/modules-load.d", "/etc/netplan", "/etc/network", "/etc/nftables.conf",
    "/etc/security", "/etc/sentinelx", "/etc/ssh", "/etc/sudoers",
    "/etc/sudoers.d", "/etc/sysctl.d", "/etc/systemd/system", "/etc/ufw",
    "/opt/hes-trade-agent",
    "/opt/hes-trade-agent/releases/737d0555f9348f1e2584714a988d0751bb4448d4",
    "/opt/hes-trade-agent/releases/f5d505567522555ee1be9c260e83085347515721",
    "/root/.config/rclone", "/root/.ssh", "/srv/hes-evidence",
    "/var/lib/apt/extended_states", "/var/lib/cloud", "/var/lib/dpkg/status",
    "/var/lib/hes-operational-health", "/var/lib/sentinelx/audit.jsonl",
    "/var/lib/sentinelx/hes-release-live-replay-8e31",
    "/var/lib/sentinelx/hes-release-manifests", "/var/lib/sentinelx/hes-runtime-snapshots",
    "/var/lib/systemd", "/var/spool/cron/crontabs",
})

def _parse_time(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        return None
    return dt.astimezone(timezone.utc)

def missing_full_paths(snapshot: dict[str, Any], required_paths: frozenset[str] = REQUIRED_FULL_PATHS) -> list[str]:
    paths = snapshot.get("paths")
    if not isinstance(paths, list) or not all(isinstance(p, str) for p in paths):
        return sorted(required_paths)
    present = set(paths)
    return sorted(required_paths - present)

def latest_full_snapshot_id(
    snapshots: list[dict[str, Any]],
    *, expected_host: str = EXPECTED_HOST,
    expected_tag: str = EXPECTED_TAG,
    required_paths: frozenset[str] = REQUIRED_FULL_PATHS,
) -> str | None:
    eligible: list[tuple[datetime, str]] = []
    for snap in snapshots:
        sid = str(snap.get("id") or "")
        dt = _parse_time(snap.get("time"))
        tags = snap.get("tags") or []
        if (sid and dt is not None and snap.get("hostname") == expected_host
                and expected_tag in tags and not missing_full_paths(snap, required_paths)):
            eligible.append((dt, sid))
    return max(eligible, key=lambda item: item[0])[1] if eligible else None

def plan_retention(
    snapshots: list[dict[str, Any]],
    today: date,
    *,
    expected_host: str = EXPECTED_HOST,
    expected_tag: str = EXPECTED_TAG,
    required_paths: frozenset[str] = REQUIRED_FULL_PATHS,
) -> dict[str, Any]:
    scoped: list[tuple[dict[str, Any], datetime]] = []
    keep: dict[str, str] = {}
    delete: dict[str, str] = {}
    partial_count = 0
    for snap in snapshots:
        sid = str(snap.get("id") or "")
        if not sid:
            keep[f"unknown-{len(keep)}"] = "MISSING_SNAPSHOT_ID_FAIL_CLOSED"
            continue
        tags = snap.get("tags") or []
        if snap.get("hostname") != expected_host or expected_tag not in tags:
            keep[sid] = "OUT_OF_SCOPE_FAIL_CLOSED"
            continue
        missing = missing_full_paths(snap, required_paths)
        if missing:
            partial_count += 1
            keep[sid] = f"PARTIAL_SCOPE_NOT_ELIGIBLE_FOR_RETENTION:{len(missing)}_MISSING_PATHS"
            continue
        dt = _parse_time(snap.get("time"))
        if dt is None:
            keep[sid] = "INVALID_TIMESTAMP_FAIL_CLOSED"
            continue
        if dt.date() > today:
            keep[sid] = "FUTURE_DATED_FAIL_CLOSED"
            continue
        scoped.append((snap, dt))

    by_day: dict[date, list[tuple[dict[str, Any], datetime]]] = {}
    for snap, dt in scoped:
        by_day.setdefault(dt.date(), []).append((snap, dt))

    newest_per_day: list[tuple[dict[str, Any], datetime]] = []
    for day, rows in by_day.items():
        latest = max(rows, key=lambda row: row[1])
        newest_per_day.append(latest)
        for snap, dt in rows:
            if snap["id"] != latest[0]["id"]:
                delete[str(snap["id"])] = "SAME_DAY_SUPERSEDED_FULL_SCOPE"

    for snap, dt in newest_per_day:
        sid = str(snap["id"])
        age = (today - dt.date()).days
        if age < POLICY["daily_days"]:
            keep[sid] = "DAILY_WINDOW"
        elif age < POLICY["monthly_first_day_days"] and dt.day == 1:
            keep[sid] = "MONTHLY_FIRST_DAY_ANCHOR"
        elif age < POLICY["weekly_sunday_days"] and dt.isoweekday() == 7:
            keep[sid] = "WEEKLY_SUNDAY_ANCHOR"
        else:
            delete[sid] = "RETENTION_EXPIRED_FULL_SCOPE"

    if scoped and not any(sid in keep for sid, _ in ((str(s["id"]), dt) for s, dt in newest_per_day)):
        snap, dt = max(scoped, key=lambda row: row[1])
        sid = str(snap["id"])
        delete.pop(sid, None)
        keep[sid] = "LATEST_FULL_SCOPE_AVAILABLE_FAIL_SAFE"

    latest_full = latest_full_snapshot_id(
        snapshots, expected_host=expected_host, expected_tag=expected_tag, required_paths=required_paths
    )
    return {
        "schema": "hes_restic_retention_plan_v2_full_scope",
        "generated_for_utc_date": today.isoformat(),
        "expected_host": expected_host,
        "expected_tag": expected_tag,
        "required_full_path_count": len(required_paths),
        "full_scope_snapshot_count": len(scoped),
        "partial_scope_snapshot_count": partial_count,
        "latest_full_snapshot_id": latest_full,
        "policy": POLICY,
        "keep": [{"snapshot_id": sid, "reason": reason} for sid, reason in sorted(keep.items())],
        "delete_candidates": [{"snapshot_id": sid, "reason": reason} for sid, reason in sorted(delete.items())],
        "stale_latest_available": any(reason == "LATEST_FULL_SCOPE_AVAILABLE_FAIL_SAFE" for reason in keep.values()),
        "deletion_authorized": False,
        "automatic_action": "NONE",
    }

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--input", type=Path, required=True, help="JSON output from restic snapshots --json")
    ap.add_argument("--today", type=date.fromisoformat, default=datetime.now(timezone.utc).date())
    args = ap.parse_args()
    raw = json.loads(args.input.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise SystemExit("snapshot JSON must be a list")
    print(json.dumps(plan_retention(raw, args.today), ensure_ascii=False, sort_keys=True))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
