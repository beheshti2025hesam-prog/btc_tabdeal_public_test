#!/usr/bin/env python3
"""Boundary-proof lineage/sequence audit for the frozen OOS snapshot.

Evidence-only: no threshold tuning, signal construction, model fitting,
promotion, or live execution. Finds the first current-main record that is
strictly beyond the frozen snapshot on BOTH sequence and event timestamp.
"""
from __future__ import annotations

import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

FROZEN_BLOB_SHA = "1a44d52a0588deb765bbbea04bfb5783dcb1050b"
FROZEN_SOURCE_COMMIT = "b8c4fe4fa054dbfa4fca17d2f307d269c16335e1"
FROZEN_SOURCE_RUN_ID = 36489452534


def git_blob_sha(data: bytes) -> str:
    header = f"blob {len(data)}\0".encode()
    return hashlib.sha1(header + data).hexdigest()


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def parse_ts(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def read_rows(path: Path):
    with path.open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def audit(frozen_path: Path, current_path: Path) -> dict:
    frozen_bytes = frozen_path.read_bytes()
    current_bytes = current_path.read_bytes()

    frozen = read_rows(frozen_path)
    current = read_rows(current_path)
    assert frozen, "frozen snapshot is empty"
    assert current, "current data is empty"

    fseq = [int(r["sequence"]) for r in frozen]
    cseq = [int(r["sequence"]) for r in current]
    fts = [parse_ts(r["updated"]) for r in frozen]
    cts = [parse_ts(r["updated"]) for r in current]

    frozen_dup = len(fseq) - len(set(fseq))
    current_dup = len(cseq) - len(set(cseq))
    frozen_back_seq = sum(b < a for a, b in zip(fseq, fseq[1:]))
    current_back_seq = sum(b < a for a, b in zip(cseq, cseq[1:]))
    frozen_back_ts = sum(b < a for a, b in zip(fts, fts[1:]))
    current_back_ts = sum(b < a for a, b in zip(cts, cts[1:]))

    frozen_max_seq = max(fseq)
    frozen_last_ts = max(fts)
    frozen_last_row = max(frozen, key=lambda r: (parse_ts(r["updated"]), int(r["sequence"])))

    candidates = [
        r for r in current
        if int(r["sequence"]) > frozen_max_seq and parse_ts(r["updated"]) > frozen_last_ts
    ]
    candidates.sort(key=lambda r: (parse_ts(r["updated"]), int(r["sequence"])))
    first = candidates[0] if candidates else None

    overlap_seq_boundary = [
        r for r in current
        if int(r["sequence"]) <= frozen_max_seq and parse_ts(r["updated"]) > frozen_last_ts
    ]
    overlap_ts_boundary = [
        r for r in current
        if parse_ts(r["updated"]) <= frozen_last_ts and int(r["sequence"]) > frozen_max_seq
    ]

    first_independent = None
    if first:
        first_independent = {
            "symbol": first["symbol"],
            "price": float(first["price"]),
            "amount": float(first["amount"]),
            "side": first["side"],
            "updated": parse_ts(first["updated"]).isoformat(),
            "sequence": int(first["sequence"]),
            "sequence_delta_from_frozen_max": int(first["sequence"]) - frozen_max_seq,
            "seconds_after_frozen_last_timestamp": (parse_ts(first["updated"]) - frozen_last_ts).total_seconds(),
        }

    status = (
        first_independent is not None
        and frozen_dup == 0
        and current_dup == 0
        and frozen_back_seq == 0
        and current_back_seq == 0
        and frozen_back_ts == 0
        and current_back_ts == 0
        and not overlap_seq_boundary
        and not overlap_ts_boundary
        and git_blob_sha(frozen_bytes) == FROZEN_BLOB_SHA
    )

    return {
        "status": "BOUNDARY_PROOF_GREEN" if status else "BOUNDARY_PROOF_RED",
        "evidence_only": True,
        "lineage": {
            "frozen_data_blob_sha": FROZEN_BLOB_SHA,
            "frozen_data_git_blob_sha_verified": git_blob_sha(frozen_bytes),
            "frozen_data_sha256": sha256(frozen_bytes),
            "frozen_source_commit": FROZEN_SOURCE_COMMIT,
            "frozen_source_run_id": FROZEN_SOURCE_RUN_ID,
            "current_data_git_blob_sha": git_blob_sha(current_bytes),
            "current_data_sha256": sha256(current_bytes),
        },
        "frozen_boundary": {
            "rows": len(frozen),
            "max_sequence": frozen_max_seq,
            "last_timestamp": frozen_last_ts.isoformat(),
            "last_row": {
                "updated": frozen_last_row["updated"],
                "sequence": int(frozen_last_row["sequence"]),
            },
        },
        "current_snapshot": {
            "rows": len(current),
            "min_sequence": min(cseq),
            "max_sequence": max(cseq),
            "min_timestamp": min(cts).isoformat(),
            "max_timestamp": max(cts).isoformat(),
        },
        "integrity": {
            "frozen_duplicate_sequence_count": frozen_dup,
            "current_duplicate_sequence_count": current_dup,
            "frozen_sequence_backward_count": frozen_back_seq,
            "current_sequence_backward_count": current_back_seq,
            "frozen_timestamp_backward_count": frozen_back_ts,
            "current_timestamp_backward_count": current_back_ts,
            "overlap_sequence_boundary_count": len(overlap_seq_boundary),
            "overlap_timestamp_boundary_count": len(overlap_ts_boundary),
        },
        "first_independent_record": first_independent,
        "claim_boundary": {
            "signal_created": False,
            "threshold_tuned": False,
            "model_fitting": False,
            "promotion_decision": False,
            "live_execution": False,
        },
    }


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    result = audit(root / "audit_frozen_trades.csv", root / "data" / "trades.csv")
    Path("boundary_proof_lineage_sequence_audit.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    if result["status"] != "BOUNDARY_PROOF_GREEN":
        raise SystemExit(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
