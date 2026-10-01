#!/usr/bin/env python3
"""Build and verify an immutable Snapshot Manifest from a materialized raw snapshot.

Fail-closed boundaries:
- structural corruption or missing source lineage => non-zero
- a partial materialization is never relabeled as the locked 1,049 reference population
- optional source sequence bounds are enforced when present, but are not fabricated
"""
from __future__ import annotations
import argparse
import hashlib
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

EXPECTED_REFERENCE_POPULATION = 1049
EXPECTED_REFERENCE_FOLD_COUNTS = {
    "0": 120, "1": 132, "2": 135, "3": 137,
    "4": 138, "5": 127, "6": 126, "7": 134,
}

def parse_ts(value: str) -> datetime:
    normalized = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        raise ValueError(f"naive timestamp: {value!r}")
    return parsed.astimezone(timezone.utc)

def git_blob_sha(raw: bytes) -> str:
    header = f"blob {len(raw)}\0".encode("utf-8")
    return hashlib.sha1(header + raw).hexdigest()

def load_snapshot(path: Path) -> tuple[dict[str, Any], bytes]:
    raw = path.read_bytes()
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("snapshot root must be an object")
    if not isinstance(data.get("observations"), list):
        raise ValueError("snapshot.observations must be a list")
    return data, raw

def build_manifest(data: dict[str, Any], raw: bytes, snapshot_path: str) -> dict[str, Any]:
    observations = data["observations"]
    source = data.get("source") or {}
    reference = data.get("reference_population") or {}
    required = {"fold", "symbol", "price", "amount", "side", "updated", "sequence"}

    missing_fields: list[str] = []
    for index, row in enumerate(observations):
        if not isinstance(row, dict):
            missing_fields.append(f"row[{index}]:not_object")
            continue
        missing = required - row.keys()
        if missing:
            missing_fields.append(f"row[{index}]:{','.join(sorted(missing))}")

    sequences: list[int] = []
    timestamps: list[datetime] = []
    for row in observations:
        if required.issubset(row.keys()):
            sequences.append(int(row["sequence"]))
            timestamps.append(parse_ts(str(row["updated"])))

    duplicate_sequences = len(sequences) - len(set(sequences))
    sequence_backward = sum(
        1 for previous, current in zip(sequences, sequences[1:]) if current <= previous
    )
    timestamp_backward_by_sequence = sum(
        1 for previous, current in zip(timestamps, timestamps[1:]) if current < previous
    )
    fold_counts = Counter(str(row["fold"]) for row in observations if isinstance(row, dict))

    source_rows = int(source.get("raw_blob_rows", 0) or 0)
    source_min_raw = source.get("min_sequence")
    source_max_raw = source.get("max_sequence")
    source_min_sequence = int(source_min_raw) if source_min_raw is not None else None
    source_max_sequence = int(source_max_raw) if source_max_raw is not None else None

    source_identity_ok = (
        isinstance(source.get("source_commit"), str)
        and bool(source.get("source_commit"))
        and isinstance(source.get("trades_blob_sha"), str)
        and bool(source.get("trades_blob_sha"))
        and source_rows > 0
    )
    source_bounds_ok = (
        (source_min_sequence is None or not sequences or min(sequences) >= source_min_sequence)
        and (source_max_sequence is None or not sequences or max(sequences) <= source_max_sequence)
    )
    source_lineage_ok = source_identity_ok and source_bounds_ok

    structural_integrity_ok = (
        not missing_fields
        and len(sequences) == len(observations)
        and duplicate_sequences == 0
        and sequence_backward == 0
        and timestamp_backward_by_sequence == 0
        and source_lineage_ok
        and int(data.get("extraction", {}).get("replacement_rows_created", 0)) == 0
    )

    actual_count = len(observations)
    exact_reference_ok = (
        actual_count == EXPECTED_REFERENCE_POPULATION
        and dict(sorted(fold_counts.items())) == EXPECTED_REFERENCE_FOLD_COUNTS
    )

    return {
        "schema_version": "snapshot-manifest.v1",
        "artifact": "HES Trade Agent — Snapshot Manifest + Integrity v1",
        "status": "PASS" if structural_integrity_ok else "FAIL",
        "snapshot": {
            "path": snapshot_path,
            "bytes": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest(),
            "git_blob_sha": git_blob_sha(raw),
            "observation_count": actual_count,
            "fold_counts": dict(sorted(fold_counts.items())),
            "source_artifact_status": data.get("status"),
        },
        "source_lineage": {
            "repository": source.get("repository"),
            "source_commit": source.get("source_commit"),
            "trades_blob_sha": source.get("trades_blob_sha"),
            "raw_blob_rows": source_rows,
            "min_sequence": source_min_sequence,
            "max_sequence": source_max_sequence,
            "bounds_available": source_min_sequence is not None and source_max_sequence is not None,
        },
        "coverage": {
            "first_timestamp_utc": timestamps[0].isoformat().replace("+00:00", "Z") if timestamps else None,
            "last_timestamp_utc": timestamps[-1].isoformat().replace("+00:00", "Z") if timestamps else None,
            "first_sequence": sequences[0] if sequences else None,
            "last_sequence": sequences[-1] if sequences else None,
        },
        "integrity": {
            "required_fields": sorted(required),
            "missing_fields": missing_fields,
            "duplicate_sequence": duplicate_sequences,
            "sequence_backward_or_equal": sequence_backward,
            "timestamp_backward_by_sequence": timestamp_backward_by_sequence,
            "source_lineage_ok": source_lineage_ok,
            "replacement_rows_created": int(data.get("extraction", {}).get("replacement_rows_created", 0)),
        },
        "reference_population": {
            "expected_evaluated": int(reference.get("expected_evaluated", EXPECTED_REFERENCE_POPULATION)),
            "expected_fold_counts": EXPECTED_REFERENCE_FOLD_COUNTS,
            "actual_observations": actual_count,
            "exact_reference_status": "PASS" if exact_reference_ok else "BLOCKED",
            "claim_rule": "Never relabel a partial mechanically materialized population as the locked 1,049 reference population.",
        },
        "gate_boundary": {
            "snapshot_integrity": "PASS" if structural_integrity_ok else "FAIL",
            "exact_1049_snapshot": "PASS" if exact_reference_ok else "BLOCKED",
            "raw_replay": "NOT_RUN",
            "candidate_performance_study": "BLOCKED" if not exact_reference_ok else "NOT_RUN",
            "signal_research_review": "BLOCKED" if not exact_reference_ok else "NOT_RUN",
            "live_execution": "DISABLED",
        },
    }

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot", required=True)
    parser.add_argument("--manifest-out", required=True)
    parser.add_argument("--check-git-blob", default=None)
    args = parser.parse_args()
    path = Path(args.snapshot)
    manifest_path = Path(args.manifest_out)
    try:
        data, raw = load_snapshot(path)
        manifest = build_manifest(data, raw, str(path))
        if args.check_git_blob and manifest["snapshot"]["git_blob_sha"] != args.check_git_blob:
            raise ValueError(
                f"snapshot Git blob mismatch: computed={manifest['snapshot']['git_blob_sha']} "
                f"expected={args.check_git_blob}"
            )
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps(manifest, indent=2, sort_keys=True))
        return 0 if manifest["status"] == "PASS" else 1
    except Exception as exc:
        print(f"SNAPSHOT_INTEGRITY_FAIL_CLOSED: {exc}", file=sys.stderr)
        return 2

if __name__ == "__main__":
    raise SystemExit(main())
