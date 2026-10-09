#!/usr/bin/env python3
"""Build a fail-closed immutable-forward snapshot candidate.

This tool records source identity and capacity only. It never evaluates
outcomes and never mutates the historical Forward OOS Lock v1.
"""
from __future__ import annotations
import csv, hashlib, json, subprocess
from datetime import datetime, timezone
from pathlib import Path

SOURCE_PATH = "data/trades.csv"
BOUNDARY = datetime.fromisoformat("2026-10-05T00:00:00+00:00")
REQUIRED_OBSERVATIONS = 3600

def parse_ts(value: str) -> datetime:
    value = value.strip()
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)

def main() -> None:
    commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], text=True
    ).strip()
    raw = subprocess.check_output(["git", "show", f"{commit}:{SOURCE_PATH}"])
    source_sha = hashlib.sha256(raw).hexdigest()

    lines = raw.decode("utf-8").splitlines()
    reader = csv.DictReader(lines)
    rows = list(reader)

    # Snapshot identity/capacity is deliberately independent of strategy
    # outcomes. One-minute capacity is represented by distinct UTC minute
    # buckets, not raw trade-row count.
    eligible = []
    for row in rows:
        ts_value = row.get("timestamp") or row.get("event_time") or row.get("time")
        if not ts_value:
            continue
        try:
            ts = parse_ts(ts_value)
        except (TypeError, ValueError):
            continue
        if ts > BOUNDARY:
            eligible.append((ts, row))

    eligible.sort(key=lambda item: item[0])
    timestamps = [ts for ts, _ in eligible]
    strict_ts = all(a < b for a, b in zip(timestamps, timestamps[1:]))
    unique_ts = len(set(timestamps)) == len(timestamps)

    minute_buckets = {ts.replace(second=0, microsecond=0) for ts in timestamps}

    result = {
        "artifact": "immutable_forward_snapshot_candidate_v1",
        "status": "IMMUTABLE_CANDIDATE_ACCUMULATING" if len(minute_buckets) < REQUIRED_OBSERVATIONS else "READY_FOR_IMMUTABLE_SOURCE_LOCK",
        "source_commit": commit,
        "source_path": SOURCE_PATH,
        "source_sha256": source_sha,
        "boundary_timestamp": BOUNDARY.isoformat(),
        "eligibility": "event timestamp strictly greater than boundary",
        "forward_trade_rows": len(eligible),
        "forward_unique_one_minute_observations": len(minute_buckets),
        "required_one_minute_observations": REQUIRED_OBSERVATIONS,
        "timestamp_strictly_increasing_after_sort": strict_ts,
        "timestamp_unique": unique_ts,
        "outcomes_inspected": False,
        "threshold_tuned": False,
        "winner_reselected": False,
        "records_deleted": False,
        "protocol_mutation": False,
        "live_execution": False,
        "promotion": "BLOCKED",
        "verdict": (
            "ACCUMULATING: insufficient valid one-minute observations for the locked 8-fold protocol."
            if len(minute_buckets) < REQUIRED_OBSERVATIONS
            else "CAPACITY_REACHED: candidate requires independent validation before immutable source lock."
        ),
    }
    Path("immutable_forward_snapshot_candidate_v1.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, indent=2))

if __name__ == "__main__":
    main()
