"""Fresh Snapshot Integrity Gate v1.

This gate validates the lineage contract without reading or rewriting live data.
It is intentionally fail-closed: missing evidence is a failure, not an inference.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path

LOCK = Path("research/fresh_snapshot_lineage_v1.json")
RESULT = Path("research/snapshot_integrity_result_v1.json")

REQUIRED = [
    "source", "frozen_boundary", "snapshot_head",
    "lineage_rule", "evaluation_boundary"
]

def main() -> None:
    if not LOCK.exists():
        raise SystemExit("FAIL: snapshot lineage lock missing")

    lock = json.loads(LOCK.read_text())
    missing = [k for k in REQUIRED if k not in lock]
    if missing:
        raise SystemExit(f"FAIL: missing lineage fields: {missing}")

    source = lock["source"]
    boundary = lock["frozen_boundary"]
    head = lock["snapshot_head"]
    rules = lock["lineage_rule"]

    assert source["source_ref"] == "main"
    assert len(source["source_commit"]) == 40
    assert len(source["trades_blob_sha"]) == 40
    assert int(boundary["first_independent_sequence"]) > 0
    assert int(head["max_sequence"]) >= int(boundary["first_independent_sequence"])
    assert boundary["first_independent_timestamp_utc"] < head["max_timestamp_utc"]

    for key in (
        "sequence_monotonicity_required",
        "timestamp_monotonicity_by_sequence_required",
        "event_id_uniqueness_required",
    ):
        assert rules[key] is True

    # The repository can prove the lock's internal consistency here.
    # Raw-row replay remains a separate execution step and cannot be inferred.
    payload = LOCK.read_bytes()
    result = {
        "artifact": "HES Trade Agent Snapshot Integrity Execution v1",
        "status": "lineage-lock-internally-valid",
        "lock_sha256": hashlib.sha256(payload).hexdigest(),
        "source_commit": source["source_commit"],
        "trades_blob_sha": source["trades_blob_sha"],
        "first_independent_sequence": boundary["first_independent_sequence"],
        "first_independent_timestamp_utc": boundary["first_independent_timestamp_utc"],
        "max_sequence": head["max_sequence"],
        "max_timestamp_utc": head["max_timestamp_utc"],
        "raw_row_replay": "required-before-performance-claims",
        "claim_boundary": lock["evaluation_boundary"],
    }
    RESULT.write_text(json.dumps(result, indent=2) + "\n")
    print("SNAPSHOT_LINEAGE_LOCK_VALID")

if __name__ == "__main__":
    main()
