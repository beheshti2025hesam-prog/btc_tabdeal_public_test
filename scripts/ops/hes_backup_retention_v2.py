#!/usr/bin/env python3
"""Deterministic mixed gzip/zstd local-backup retention planner."""
from __future__ import annotations
import argparse
from datetime import date, datetime, timezone
import json
from pathlib import Path
import re
from typing import Any

PATTERN = re.compile(r"^hes-full-(\d{8})T(\d{6})Z\.tar\.(gz|zst)\.gpg$")

def plan_retention(names: list[str], today: date) -> dict[str, Any]:
    parsed: list[tuple[str, date, str, str]] = []
    keep: dict[str, str] = {}
    delete: dict[str, str] = {}
    by_day: dict[str, list[tuple[str, datetime]]] = {}
    for name in names:
        match = PATTERN.fullmatch(name)
        if not match:
            keep[name] = "INVALID_NAME_FAIL_CLOSED"
            continue
        raw_day, raw_time, fmt = match.groups()
        try:
            stamp = datetime.strptime(raw_day + raw_time, "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
        except ValueError:
            keep[name] = "INVALID_DATE_FAIL_CLOSED"
            continue
        day = stamp.date()
        if day > today:
            keep[name] = "FUTURE_DATED_FAIL_CLOSED"
            continue
        parsed.append((name, day, fmt, stamp.isoformat()))
        by_day.setdefault(day.isoformat(), []).append((name, stamp))
    latest: set[str] = set()
    for rows in by_day.values():
        latest.add(max(rows, key=lambda row: row[1])[0])
    for name, day, fmt, stamp in parsed:
        if name not in latest:
            delete[name] = "SAME_DAY_SUPERSEDED"
            continue
        age = (today - day).days
        if age < 7:
            keep[name] = "DAILY_WINDOW"
        elif age < 180 and day.day == 1:
            keep[name] = "MONTHLY_FIRST_DAY_ANCHOR"
        elif age < 28 and day.isoweekday() == 7:
            keep[name] = "WEEKLY_SUNDAY_ANCHOR"
        else:
            delete[name] = "RETENTION_EXPIRED"
    return {
        "schema": "hes_backup_retention_plan_v2",
        "today_utc": today.isoformat(),
        "policy": {"daily_days": 7, "weekly_sunday_days": 28, "monthly_first_day_days": 180},
        "keep": [{"name": n, "reason": r} for n, r in sorted(keep.items())],
        "delete": [{"name": n, "reason": r} for n, r in sorted(delete.items())],
        "delete_authorized": False,
        "automatic_action": "NONE",
    }

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--directory", type=Path, required=True)
    ap.add_argument("--today", type=date.fromisoformat, required=True)
    ap.add_argument("--delete-list", action="store_true")
    args = ap.parse_args()
    if not args.directory.is_dir():
        raise SystemExit("backup directory missing")
    names = [p.name for p in args.directory.iterdir()
             if p.is_file() and (p.name.endswith(".tar.gz.gpg") or p.name.endswith(".tar.zst.gpg"))]
    report = plan_retention(names, args.today)
    if args.delete_list:
        for row in report["delete"]:
            print(row["name"])
    else:
        print(json.dumps(report, sort_keys=True))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
