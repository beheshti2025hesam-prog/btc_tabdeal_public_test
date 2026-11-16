#!/usr/bin/env python3
"""Fail-closed Dropbox capacity gate for encrypted Restic repository transfer."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from typing import Any

DEFAULT_RESERVE_BYTES = 64 * 1024 * 1024

def evaluate_capacity(repository_bytes: int, quota: dict[str, Any], reserve_bytes: int = DEFAULT_RESERVE_BYTES) -> dict[str, Any]:
    try:
        repo = int(repository_bytes)
        reserve = int(reserve_bytes)
        total = int(quota["total"])
        used = int(quota["used"])
        free = int(quota["free"])
        if min(repo, total, free) <= 0 or reserve < 0 or used < 0 or used > total:
            raise ValueError
        if total != used + free:
            raise ValueError
    except (KeyError, TypeError, ValueError, OverflowError):
        return {
            "schema": "hes_restic_offsite_capacity_gate_v1",
            "status": "BLOCKED_INVALID_OR_INCONSISTENT_CAPACITY",
            "repository_bytes": None,
            "free_bytes": None,
            "reserve_bytes": reserve_bytes if isinstance(reserve_bytes, int) else None,
            "required_bytes": None,
            "shortfall_bytes": None,
            "transfer_authorized": False,
            "automatic_action": "NONE",
        }
    required = repo + reserve
    shortfall = max(0, required - free)
    return {
        "schema": "hes_restic_offsite_capacity_gate_v1",
        "status": "PASS_CAPACITY" if shortfall == 0 else "BLOCKED_INSUFFICIENT_FREE_QUOTA",
        "repository_bytes": repo,
        "free_bytes": free,
        "reserve_bytes": reserve,
        "required_bytes": required,
        "shortfall_bytes": shortfall,
        "quota_total_bytes": total,
        "quota_used_bytes": used,
        "transfer_authorized": False,
        "automatic_action": "NONE",
        "note": "Preflight only; explicit transfer workflow and post-copy integrity/restore gates remain mandatory.",
    }

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--repository-bytes", type=int, required=True)
    ap.add_argument("--quota-json", type=Path, required=True, help="JSON from rclone about hesdropbox: --json")
    ap.add_argument("--reserve-bytes", type=int, default=DEFAULT_RESERVE_BYTES)
    args = ap.parse_args()
    quota = json.loads(args.quota_json.read_text(encoding="utf-8"))
    report = evaluate_capacity(args.repository_bytes, quota, args.reserve_bytes)
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0 if report["status"] == "PASS_CAPACITY" else 20

if __name__ == "__main__":
    raise SystemExit(main())
