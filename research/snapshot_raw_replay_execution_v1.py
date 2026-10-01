"""Fresh Snapshot Raw Replay Gate v1.

Fail-closed replay of the exact snapshot lineage locked for controlled research.
No signal construction, tuning, model fitting, or live execution is performed.
"""
from __future__ import annotations

import csv
import hashlib
import json
import subprocess
from datetime import datetime
from pathlib import Path

LOCK = Path("research/fresh_snapshot_lineage_v1.json")
RESULT = Path("research/snapshot_raw_replay_result_v1.json")
TRADES = Path("data/trades.csv")


def git_blob_sha(path: Path) -> str:
    return subprocess.check_output(
        ["git", "hash-object", str(path)], text=True
    ).strip()


def parse_ts(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def main() -> None:
    if not LOCK.exists() or not TRADES.exists():
        raise SystemExit("FAIL: required lineage lock or raw snapshot missing")

    lock = json.loads(LOCK.read_text())
    source = lock["source"]
    boundary = lock["frozen_boundary"]

    actual_blob = git_blob_sha(TRADES)
    expected_blob = source["trades_blob_sha"]
    if actual_blob != expected_blob:
        raise SystemExit(
            f"FAIL: trades blob mismatch: expected {expected_blob}, got {actual_blob}"
        )

    expected_seq = int(boundary["first_independent_sequence"])
    expected_ts = parse_ts(boundary["first_independent_timestamp_utc"])

    required = {"symbol", "price", "amount", "side", "updated", "sequence"}
    event_id_names = {"event_id", "eventId", "id"}
    row_count = 0
    post_boundary_rows = 0
    first_post_seq = None
    first_post_ts = None
    last_seq = None
    last_ts = None
    duplicate_sequence = 0
    sequence_backward = 0
    timestamp_backward = 0
    event_ids = set()
    event_id_duplicates = 0
    event_id_field = None
    min_seq = None
    max_seq = None
    min_ts = None
    max_ts = None

    with TRADES.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        fields = set(reader.fieldnames or [])
        missing = sorted(required - fields)
        if missing:
            raise SystemExit(f"FAIL: raw snapshot missing required fields: {missing}")
        event_id_field = next((x for x in reader.fieldnames if x in event_id_names), None)
        if event_id_field is None:
            raise SystemExit(
                "FAIL: event-id uniqueness cannot be proven: no event_id/id field in raw snapshot"
            )

        for row in reader:
            row_count += 1
            seq = int(row["sequence"])
            ts = parse_ts(row["updated"])

            if last_seq is not None:
                if seq < last_seq:
                    sequence_backward += 1
                elif seq == last_seq:
                    duplicate_sequence += 1
                if ts < last_ts:
                    timestamp_backward += 1

            last_seq = seq
            last_ts = ts
            min_seq = seq if min_seq is None else min(min_seq, seq)
            max_seq = seq if max_seq is None else max(max_seq, seq)
            min_ts = ts if min_ts is None else min(min_ts, ts)
            max_ts = ts if max_ts is None else max(max_ts, ts)

            if event_id_field:
                eid = row[event_id_field]
                if eid in event_ids:
                    event_id_duplicates += 1
                event_ids.add(eid)

            if seq >= expected_seq and first_post_seq is None:
                first_post_seq = seq
                first_post_ts = ts

            if seq > expected_seq:
                post_boundary_rows += 1

    if first_post_seq != expected_seq:
        raise SystemExit(
            f"FAIL: first independent sequence not preserved: expected {expected_seq}, got {first_post_seq}"
        )
    if first_post_ts != expected_ts:
        raise SystemExit(
            f"FAIL: first independent timestamp mismatch: expected {expected_ts.isoformat()}, got {first_post_ts.isoformat() if first_post_ts else None}"
        )
    if duplicate_sequence or sequence_backward or timestamp_backward or event_id_duplicates:
        raise SystemExit(
            "FAIL: raw snapshot integrity violation: "
            f"duplicate_sequence={duplicate_sequence}, "
            f"sequence_backward={sequence_backward}, "
            f"timestamp_backward={timestamp_backward}, "
            f"event_id_duplicates={event_id_duplicates}"
        )

    result = {
        "artifact": "HES Trade Agent Fresh Snapshot Raw Replay v1",
        "status": "raw-replay-valid",
        "source_commit": source["source_commit"],
        "expected_trades_blob_sha": expected_blob,
        "actual_trades_blob_sha": actual_blob,
        "row_count": row_count,
        "min_sequence": min_seq,
        "max_sequence": max_seq,
        "min_timestamp_utc": min_ts.isoformat(),
        "max_timestamp_utc": max_ts.isoformat(),
        "first_independent_sequence": expected_seq,
        "first_independent_timestamp_utc": expected_ts.isoformat(),
        "post_boundary_rows": post_boundary_rows,
        "duplicate_sequence": duplicate_sequence,
        "sequence_backward": sequence_backward,
        "timestamp_backward_by_sequence": timestamp_backward,
        "event_id_field": event_id_field,
        "event_id_duplicates": event_id_duplicates,
        "claim_boundary": lock["evaluation_boundary"],
    }
    RESULT.write_text(json.dumps(result, indent=2) + "\n")
    print("SNAPSHOT_RAW_REPLAY_VALID")


if __name__ == "__main__":
    main()
