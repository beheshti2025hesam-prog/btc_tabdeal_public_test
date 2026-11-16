#!/usr/bin/env python3
"""Read-only retention planner for HES Restic snapshots."""
from __future__ import annotations
import argparse
from datetime import date, datetime, timezone
import json
from pathlib import Path
from typing import Any

POLICY = {"daily_days": 7, "weekly_sunday_days": 28, "monthly_first_day_days": 180}
EXPECTED_TAG = "hes-core-v1"
EXPECTED_HOST = "hes-trade-agent"

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

def plan_retention(
    snapshots: list[dict[str, Any]],
    today: date,
    *,
    expected_host: str = EXPECTED_HOST,
    expected_tag: str = EXPECTED_TAG,
) -> dict[str, Any]:
    scoped: list[tuple[dict[str, Any], datetime]] = []
    keep: dict[str, str] = {}
    delete: dict[str, str] = {}
    for snap in snapshots:
        sid = str(snap.get("id") or "")
        if not sid:
            keep[f"unknown-{len(keep)}"] = "MISSING_SNAPSHOT_ID_FAIL_CLOSED"
            continue
        tags = snap.get("tags") or []
        if snap.get("hostname") != expected_host or expected_tag not in tags:
            keep[sid] = "OUT_OF_SCOPE_FAIL_CLOSED"
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
                delete[str(snap["id"])] = "SAME_DAY_SUPERSEDED"

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
            delete[sid] = "RETENTION_EXPIRED"

    # Never leave the repository without a snapshot if all available snapshots
    # are older than policy windows; preserve the newest and raise a stale warning.
    if scoped and not keep:
        snap, dt = max(scoped, key=lambda row: row[1])
        sid = str(snap["id"])
        delete.pop(sid, None)
        keep[sid] = "LATEST_AVAILABLE_FAIL_SAFE"

    return {
        "schema": "hes_restic_retention_plan_v1",
        "generated_for_utc_date": today.isoformat(),
        "expected_host": expected_host,
        "expected_tag": expected_tag,
        "policy": POLICY,
        "keep": [{"snapshot_id": sid, "reason": reason} for sid, reason in sorted(keep.items())],
        "delete_candidates": [{"snapshot_id": sid, "reason": reason} for sid, reason in sorted(delete.items())],
        "stale_latest_available": any(x["reason"] == "LATEST_AVAILABLE_FAIL_SAFE" for x in
                                      [{"reason": r} for r in keep.values()]),
        "deletion_authorized": False,
        "automatic_action": "NONE"
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
